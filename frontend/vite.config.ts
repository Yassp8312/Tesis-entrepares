import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import type { UserConfig } from 'vite';

export function apiTarget(value = 'http://127.0.0.1:8000'): string {
  let url: URL;
  try { url = new URL(value); }
  catch { throw new Error('ENTREPARES_API_TARGET debe ser un origen local válido.'); }
  if (!['http:', 'https:'].includes(url.protocol)
    || !['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname)
    || url.username || url.password || url.pathname !== '/' || url.search || url.hash) {
    throw new Error('ENTREPARES_API_TARGET debe ser un origen local sin credenciales.');
  }
  return url.origin;
}

export function frontendConfig(command: 'build' | 'serve'): UserConfig {
  return {
    plugins: [vue()],
    base: command === 'build' ? '/static/entrepares/' : '/',
    build: { manifest: true },
    envDir: false,
    envPrefix: [],
    server: {
      host: '127.0.0.1', port: 5173, strictPort: true,
      proxy: {
        '^/(?:api|admin|static)(?:/|$)': {
          target: apiTarget(process.env.ENTREPARES_API_TARGET),
          // Conservar Host y Origin permite comprobar CSRF bajo el origen del navegador.
          changeOrigin: false,
        },
      },
    },
    preview: { host: '127.0.0.1', port: 4173, strictPort: true },
  };
}

export default defineConfig(({ command }) => frontendConfig(command));
