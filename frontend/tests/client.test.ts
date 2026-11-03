import assert from 'node:assert/strict';
import test from 'node:test';
import { createApiClient } from '../src/api/client.ts';
import { ApiClientError, isApiProblem } from '../src/api/errors.ts';

const ID = '583049c5-6470-460a-8c51-d4b7076e95de';
const TOKEN = 'a'.repeat(64);
const SECRET = 'dato-sintetico-que-no-debe-reflejarse';
function reply(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json', 'X-Request-ID': ID } });
}
function problem(code = 'FORBIDDEN', id = ID) {
  return { code, message: 'No tienes permiso.', fields: [], request_id: id };
}
const matches = (kind: string) => (error: unknown) => error instanceof ApiClientError && error.kind === kind;

test('GET conserva el origen, no añade CSRF y codifica cada filtro una sola vez', async () => {
  let calls = 0;
  const api = createApiClient(async (url, init) => {
    calls++;
    assert.equal(url, '/api/v1/opportunities/?q=salud+%26+dise%C3%B1o&funded=false&page=0');
    assert.equal(init.credentials, 'same-origin'); assert.equal(init.mode, 'same-origin');
    assert.equal(init.redirect, 'error'); assert.equal(init.cache, 'no-store');
    const headers = new Headers(init.headers);
    assert.equal(headers.get('Accept'), 'application/json');
    assert.equal(headers.get('X-CSRFToken'), null); assert.equal(headers.get('Content-Type'), null);
    return reply({ count: 0 });
  });
  assert.deepEqual(await api.request('opportunities/', { query: { q: 'salud & diseño', funded: false, page: 0, omitted: undefined } }), { count: 0 });
  assert.equal(calls, 1);
});

for (const path of ['https://ajeno.example/x', '//ajeno.example', '../auth/', 'profiles/../auth/', 'profiles/%2e%2e/', 'profiles\\x', '/auth/login/', 'auth/login/?x=1', 'auth/login/#x']) {
  test(`una ruta fuera del contrato se rechaza antes de enviar: ${path}`, async () => {
    let calls = 0; const api = createApiClient(async () => { calls++; return reply({}); });
    await assert.rejects(api.request(path), TypeError); assert.equal(calls, 0);
  });
}

test('contexto organizacional explícito no se cambia ni se elimina', async () => {
  const api = createApiClient(async (_url, init) => { assert.equal(new Headers(init.headers).get('X-Organization-ID'), ID); return reply(problem(), 403); });
  await assert.rejects(api.request('directory/profiles/', { organizationId: ID }), matches('api'));
});

test('errores de datos locales no envían solicitudes', async () => {
  let calls = 0; const api = createApiClient(async () => { calls++; return reply({}); });
  await assert.rejects(api.request('x/', { organizationId: 'inválido' }), TypeError);
  await assert.rejects(api.request('x/', { body: {} }), TypeError);
  await assert.rejects(api.request('x/', { method: 'POST', body: { amount: Infinity } }), TypeError);
  await assert.rejects(api.request('x/', { query: { page: NaN } }), TypeError);
  await assert.rejects(api.request('x/', { timeoutMs: 2**32 }), TypeError);
  assert.equal(calls, 0);
});

test('mutaciones concurrentes comparten una comprobación CSRF y mantienen sus cuerpos', async () => {
  let release!: (value: Response) => void;
  const gate = new Promise<Response>(resolve => { release = resolve; });
  let bootstraps = 0; let mutations = 0;
  const api = createApiClient(async (url, init) => {
    if (url.endsWith('auth/csrf/')) { bootstraps++; return gate; }
    mutations++; assert.equal(new Headers(init.headers).get('X-CSRFToken'), TOKEN);
    assert.equal(new Headers(init.headers).get('Content-Type'), 'application/json');
    assert.deepEqual(JSON.parse(String(init.body)), { title: 'sintético' });
    return reply({ accepted: true });
  });
  const first = api.request('opportunities/', { method: 'POST', body: { title: 'sintético' } });
  const second = api.request('opportunities/', { method: 'PATCH', body: { title: 'sintético' } });
  assert.equal(bootstraps, 1); assert.equal(mutations, 0);
  release(reply({ csrf_token: TOKEN }));
  await Promise.all([first, second]); assert.equal(mutations, 2);
});

test('bootstrap no implementado falla sin publicar la mutación ni fingir un token', async () => {
  const calls: string[] = [];
  const api = createApiClient(async (url) => { calls.push(url); return reply(problem('NOT_FOUND'), 404); });
  await assert.rejects(api.request('auth/register/', { method: 'POST', body: {} }), matches('api'));
  assert.deepEqual(calls, ['/api/v1/auth/csrf/']);
});

test('respuesta de token incorrecta no permite llegar al POST', async () => {
  let calls = 0; const api = createApiClient(async () => { calls++; return reply({ csrf_token: 'cabecera\ninsegura' }); });
  await assert.rejects(api.request('x/', { method: 'POST' }), matches('invalid-response')); assert.equal(calls, 1);
});

test('CSRF_FAILED invalida caché sin repetir la mutación automáticamente', async () => {
  let gets = 0; let posts = 0;
  const api = createApiClient(async (url, init) => {
    if (url.endsWith('auth/csrf/')) { gets++; return reply({ csrf_token: String.fromCharCode(96 + gets).repeat(64) }); }
    posts++; assert.equal(new Headers(init.headers).get('X-CSRFToken'), String.fromCharCode(96 + posts).repeat(64));
    return posts === 1 ? reply(problem('CSRF_FAILED'), 403) : reply({ accepted: true });
  });
  await assert.rejects(api.request('x/', { method: 'POST' }), matches('api'));
  assert.equal(posts, 1);
  await api.request('x/', { method: 'POST' }); assert.equal(gets, 2); assert.equal(posts, 2);
});

test('un token renovado desde sesión sustituye al anterior y reset descarta la caché', async () => {
  let gets = 0;
  const api = createApiClient(async (url, init) => {
    if (url.endsWith('auth/csrf/')) { gets++; return reply({ csrf_token: TOKEN }); }
    assert.equal(new Headers(init.headers).get('X-CSRFToken'), 'b'.repeat(64)); return new Response(null, { status: 204, headers: { 'X-Request-ID': ID } });
  });
  await api.prepareCsrf(); api.setCsrfToken('b'.repeat(64));
  assert.equal(await api.request('auth/logout/', { method: 'POST' }), undefined);
  assert.equal(gets, 1); api.resetCsrf(); await api.prepareCsrf(); assert.equal(gets, 2);
  assert.throws(() => api.setCsrfToken('x\r\n'), TypeError);
});

test('una comprobación iniciada antes de reset no repuebla la caché', async () => {
  let release!: (response: Response) => void; let gets = 0;
  const api = createApiClient(async () => { gets++; return gets === 1 ? new Promise(resolve => { release = resolve; }) : reply({ csrf_token: 'b'.repeat(64) }); });
  const pending = api.prepareCsrf(); api.resetCsrf(); release(reply({ csrf_token: TOKEN }));
  await assert.rejects(pending, matches('csrf-reset'));
  assert.equal(await api.prepareCsrf(), 'b'.repeat(64));
});

test('cancelar un participante no cancela el bootstrap compartido por otro', async () => {
  let release!: (value: Response) => void; let posts = 0;
  const gate = new Promise<Response>(resolve => { release = resolve; });
  const api = createApiClient(async (url) => {
    if (url.endsWith('auth/csrf/')) return gate;
    posts++; return reply({ accepted: true });
  });
  const controller = new AbortController();
  const first = api.request('x/', { method: 'POST', signal: controller.signal });
  const second = api.request('x/', { method: 'POST' });
  controller.abort(); await assert.rejects(first, matches('aborted'));
  release(reply({ csrf_token: TOKEN })); await second; assert.equal(posts, 1);
});

test('un error público válido conserva campos, estado y correlación', async () => {
  const data = { ...problem('VALIDATION_ERROR'), fields: [{ path: 'contacts[0].value', code: 'required', message: 'Campo obligatorio.' }] };
  const api = createApiClient(async () => reply(data, 400));
  await assert.rejects(api.request('x/'), error => error instanceof ApiClientError && error.status === 400 && error.requestId === ID && error.problem?.fields[0].path === 'contacts[0].value');
});

for (const variant of ['html', 'json-invalido', 'sin-id', 'id-distinto', 'campos-extra']) {
  test(`una respuesta inesperada no expone cuerpo o mensajes internos: ${variant}`, async () => {
    const api = createApiClient(async () => {
      if (variant === 'html') return new Response(SECRET, { status: 500, headers: { 'X-Request-ID': ID, 'Content-Type': 'text/html' } });
      if (variant === 'json-invalido') return new Response('{'+SECRET, { status: 500, headers: { 'X-Request-ID': ID, 'Content-Type': 'application/json' } });
      if (variant === 'sin-id') return new Response(JSON.stringify(problem()), { status: 500, headers: { 'Content-Type': 'application/json' } });
      if (variant === 'id-distinto') return reply(problem('FORBIDDEN', 'f93f0f78-a159-4c19-9362-80717e6ef3ed'), 403);
      return reply({ ...problem(), private: SECRET }, 403);
    });
    await assert.rejects(api.request('x/'), error => error instanceof ApiClientError && error.kind === 'invalid-response' && !error.message.includes(SECRET));
  });
}

test('la forma de ApiError respeta límites y rechaza valores blancos o adicionales', () => {
  assert.ok(isApiProblem(problem()));
  assert.equal(isApiProblem({ ...problem(), fields: new Array(101).fill({ path: 'x', code: 'x', message: 'x' }) }), false);
  assert.equal(isApiProblem({ ...problem(), message: ' ' }), false);
  assert.equal(isApiProblem({ ...problem(), code: 'x'.repeat(81) }), false);
  assert.equal(isApiProblem({ ...problem(), fields: [{ path: 'x', code: 'x', message: 'x', private: SECRET }] }), false);
});

test('fallo de red oculta detalles internos y no reintenta', async () => {
  let calls = 0; const api = createApiClient(async () => { calls++; throw new TypeError(SECRET); });
  await assert.rejects(api.request('x/'), error => error instanceof ApiClientError && error.kind === 'network' && !error.message.includes(SECRET)); assert.equal(calls, 1);
});

test('cancelación previa evita incluso el bootstrap', async () => {
  const controller = new AbortController(); controller.abort(); let calls = 0;
  const api = createApiClient(async () => { calls++; return reply({}); });
  await assert.rejects(api.request('x/', { method: 'POST', signal: controller.signal }), matches('aborted')); assert.equal(calls, 0);
});

test('plazo y cancelación detienen la espera de fetch con error diferenciado', async () => {
  const api = createApiClient((_url, init) => new Promise((_resolve, reject) => {
    init.signal!.addEventListener('abort', () => reject(new Error(SECRET)), { once: true });
  }));
  await assert.rejects(api.request('x/', { timeoutMs: 5 }), matches('timeout'));
  const controller = new AbortController(); const pending = api.request('x/', { signal: controller.signal }); controller.abort();
  await assert.rejects(pending, matches('aborted'));
});
