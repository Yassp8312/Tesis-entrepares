import assert from 'node:assert/strict';
import test from 'node:test';
import { createMemoryHistory } from 'vue-router';
import { createAppRouter } from '../src/router.ts';
import config, { apiTarget } from '../vite.config.ts';

test('el router resuelve inicio, presentación, anclas y una página inexistente', () => {
  const router = createAppRouter(createMemoryHistory());
  assert.equal(router.resolve('/').name, 'home');
  assert.equal(router.resolve('/acerca-de#personas').name, 'about');
  assert.equal(router.resolve('/acerca-de#personas').hash, '#personas');
  assert.equal(router.resolve('/no-existe').name, 'not-found');
});

test('el proxy es local, mantiene el origen y excluye espacios del servidor del fallback Vue', () => {
  const options = config as Exclude<typeof config, Function | Promise<unknown>>;
  assert.equal(options.envDir, false);
  assert.deepEqual(options.envPrefix, []);
  assert.equal(options.server?.host, '127.0.0.1');
  const [pattern, proxy] = Object.entries(options.server!.proxy!)[0];
  const matcher = new RegExp(pattern);
  for (const route of ['/api', '/api/v1/x/', '/admin/', '/static/x.css']) assert.ok(matcher.test(route));
  assert.equal(matcher.test('/apiary'), false);
  assert.equal((proxy as { changeOrigin: boolean }).changeOrigin, false);
});

for (const input of ['https://ajeno.example', 'http://user:secret@127.0.0.1:8000', 'file:///tmp/x', 'http://127.0.0.1/x', 'http://127.0.0.1/?token=x', 'inválido']) {
  test(`configuración del proxy rechaza destino no permitido: ${input.split('@').at(-1)}`, () => {
    assert.throws(() => apiTarget(input));
  });
}
