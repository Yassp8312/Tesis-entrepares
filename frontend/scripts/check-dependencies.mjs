import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vue from '@vitejs/plugin-vue';
import { build } from 'vite';
import { createMemoryHistory, createRouter } from 'vue-router';

const root = fileURLToPath(new URL('..', import.meta.url));
const require = createRequire(import.meta.url);
const manifest = JSON.parse(await readFile(path.join(root, 'package.json'), 'utf8'));
assert.equal(process.versions.node, manifest.engines.node, 'Versión de Node distinta de la fijada');

// Se construye una muestra técnica aislada, sin crear pantallas del producto.
const probe = path.join(root, '.cache', 'dependency-probe');
await mkdir(probe, { recursive: true });
await writeFile(path.join(probe, 'index.html'), '<div id="app"></div><script type="module" src="/main.ts"></script>\n');
await writeFile(path.join(probe, 'main.ts'), "import { createApp } from 'vue';\nimport App from './App.vue';\ncreateApp(App).mount('#app');\n");
await writeFile(path.join(probe, 'App.vue'), '<script setup lang="ts">\nconst mensaje: string = "Comprobación técnica de dependencias";\n</script>\n<template><p>{{ mensaje }}</p></template>\n');
await writeFile(path.join(probe, 'tsconfig.json'), JSON.stringify({
  compilerOptions: {
    target: 'ES2022', module: 'ESNext', moduleResolution: 'Bundler',
    lib: ['ES2022', 'DOM'], strict: true, isolatedModules: true,
    skipLibCheck: true, noEmit: true, types: [],
  },
  include: ['*.ts', '*.vue'],
}, null, 2) + '\n');

const checkerManifest = require.resolve('vue-tsc/package.json');
const checker = JSON.parse(await readFile(checkerManifest, 'utf8'));
const checkerBin = typeof checker.bin === 'string' ? checker.bin : checker.bin['vue-tsc'];
const checked = spawnSync(process.execPath, [path.resolve(path.dirname(checkerManifest), checkerBin), '--noEmit', '--project', path.join(probe, 'tsconfig.json')], { cwd: root, stdio: 'inherit' });
if (checked.error) throw checked.error;
assert.equal(checked.status, 0, 'Falló la comprobación de tipos Vue y TypeScript');

const output = await build({
  configFile: false, root: probe, plugins: [vue()], logLevel: 'warn',
  build: { outDir: path.join(probe, 'dist'), emptyOutDir: true, write: false },
});
const bundles = Array.isArray(output) ? output : [output];
assert.ok(bundles.some(result => result.output.some(asset => asset.type === 'chunk' && asset.isEntry)), 'Falta el módulo JavaScript compilado');

const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/comprobacion', component: { template: '<p>Comprobación</p>' } }] });
await router.push('/comprobacion');
await router.isReady();
assert.equal(router.currentRoute.value.path, '/comprobacion');
console.log('Correcto: tipos Vue/TypeScript, compilación Vite y navegación en memoria.');
