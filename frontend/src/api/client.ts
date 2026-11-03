import { ApiClientError, isApiProblem, isUuid } from './errors.ts';

export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };
export interface RequestOptions {
  method?: 'GET' | 'HEAD' | 'OPTIONS' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: JsonValue;
  query?: Record<string, string | number | boolean | undefined>;
  organizationId?: string;
  signal?: AbortSignal;
  timeoutMs?: number;
}
type Fetcher = (input: string, init: RequestInit) => Promise<Response>;
const SAFE = new Set(['GET', 'HEAD', 'OPTIONS']);
const TOKEN = /^[A-Za-z0-9]+$/;

function isToken(value: unknown): value is string {
  return typeof value === 'string' && value.length >= 1 && value.length <= 512 && TOKEN.test(value);
}

function apiUrl(path: string, query: RequestOptions['query']): string {
  if (path !== '' && !/^[A-Za-z0-9_-]+(?:\/[A-Za-z0-9_-]+)*\/?$/.test(path)) {
    throw new TypeError('La ruta debe ser relativa al espacio de API.');
  }
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === undefined) continue;
    if (typeof value === 'number' && !Number.isFinite(value)) throw new TypeError('Parámetro numérico no finito.');
    params.set(key, String(value));
  }
  return '/api/v1/' + path + (params.size ? '?' + params.toString() : '');
}

async function waitFor<T>(promise: Promise<T>, signal: AbortSignal): Promise<T> {
  if (signal.aborted) throw new ApiClientError('aborted');
  let onAbort: () => void;
  const aborted = new Promise<never>((_resolve, reject) => {
    onAbort = () => reject(new ApiClientError('aborted'));
    signal.addEventListener('abort', onAbort, { once: true });
  });
  try { return await Promise.race([promise, aborted]); }
  finally { signal.removeEventListener('abort', onAbort!); }
}

export function createApiClient(fetcher: Fetcher = (url, init) => fetch(url, init)) {
  let csrfToken: string | null = null;
  let csrfFlight: Promise<string> | null = null;
  let generation = 0;

  function resetCsrf() { generation++; csrfToken = null; csrfFlight = null; }
  function setCsrfToken(token: string) {
    if (!isToken(token)) throw new TypeError('Token CSRF no válido.');
    resetCsrf(); csrfToken = token;
  }

  async function prepareCsrf(): Promise<string> {
    if (csrfToken) return csrfToken;
    if (csrfFlight) return csrfFlight;
    const current = generation;
    const task = (async () => {
      const data = await request('auth/csrf/');
      if (typeof data !== 'object' || data === null || Array.isArray(data)
        || Object.keys(data).length !== 1 || !('csrf_token' in data) || !isToken(data.csrf_token)) {
        throw new ApiClientError('invalid-response');
      }
      if (current !== generation) throw new ApiClientError('csrf-reset');
      csrfToken = data.csrf_token;
      return csrfToken;
    })().finally(() => { if (csrfFlight === task) csrfFlight = null; });
    csrfFlight = task;
    return task;
  }

  async function request(path: string, options: RequestOptions = {}): Promise<unknown> {
    const method = options.method ?? 'GET';
    const url = apiUrl(path, options.query);
    if (SAFE.has(method) && options.body !== undefined) throw new TypeError('El método no admite cuerpo.');
    if (options.organizationId !== undefined && !isUuid(options.organizationId)) throw new TypeError('Contexto organizacional no válido.');
    const timeoutMs = options.timeoutMs ?? 30_000;
    if (!Number.isInteger(timeoutMs) || timeoutMs <= 0 || timeoutMs > 2_147_483_647) throw new TypeError('Plazo de solicitud no válido.');
    const body = options.body === undefined ? undefined : JSON.stringify(options.body, (_key, value: unknown) => {
      if (typeof value === 'number' && !Number.isFinite(value)) throw new TypeError('Valor JSON no finito.');
      return value;
    });
    const controller = new AbortController();
    const cancel = () => controller.abort();
    options.signal?.addEventListener('abort', cancel, { once: true });
    if (options.signal?.aborted) controller.abort();
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
    try {
      if (controller.signal.aborted) throw new ApiClientError('aborted');
      const headers = new Headers({ Accept: 'application/json' });
      if (body !== undefined) headers.set('Content-Type', 'application/json');
      if (options.organizationId) headers.set('X-Organization-ID', options.organizationId);
      if (!SAFE.has(method)) headers.set('X-CSRFToken', await waitFor(prepareCsrf(), controller.signal));
      const response = await fetcher(url, {
        method, headers, body, signal: controller.signal,
        credentials: 'same-origin', mode: 'same-origin', redirect: 'error', cache: 'no-store',
      });
      const headerId = response.headers.get('X-Request-ID');
      const requestId = isUuid(headerId) ? headerId : null;
      if (!requestId) throw new ApiClientError('invalid-response', response.status);
      if (response.status === 204 || method === 'HEAD' && response.ok) return undefined;
      if (response.headers.get('Content-Type')?.split(';')[0].trim().toLowerCase() !== 'application/json') {
        throw new ApiClientError('invalid-response', response.status, requestId);
      }
      let data: unknown;
      try { data = await response.json(); }
      catch { throw new ApiClientError('invalid-response', response.status, requestId); }
      if (!response.ok) {
        if (!isApiProblem(data) || data.request_id !== requestId) throw new ApiClientError('invalid-response', response.status, requestId);
        if (data.code === 'CSRF_FAILED') resetCsrf();
        throw new ApiClientError('api', response.status, requestId, data);
      }
      return data;
    } catch (error) {
      if (timedOut) throw new ApiClientError('timeout');
      if (controller.signal.aborted) throw new ApiClientError('aborted');
      if (error instanceof ApiClientError) throw error;
      throw new ApiClientError('network');
    } finally {
      clearTimeout(timer);
      options.signal?.removeEventListener('abort', cancel);
    }
  }

  return { request, prepareCsrf, resetCsrf, setCsrfToken };
}

export const api = createApiClient();
