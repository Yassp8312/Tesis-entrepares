export interface FieldError { path: string; code: string; message: string }
export interface ApiProblem { code: string; message: string; fields: FieldError[]; request_id: string }
export type ClientErrorKind = 'api' | 'network' | 'timeout' | 'aborted' | 'invalid-response' | 'csrf-reset';

export class ApiClientError extends Error {
  readonly kind: ClientErrorKind;
  readonly status: number | null;
  readonly requestId: string | null;
  readonly problem: ApiProblem | null;

  constructor(kind: ClientErrorKind, status: number | null = null, requestId: string | null = null, problem: ApiProblem | null = null) {
    const messages: Record<Exclude<ClientErrorKind, 'api'>, string> = {
      network: 'No se pudo completar la comunicación. Comprueba tu conexión y el estado de la operación.',
      timeout: 'La solicitud tardó demasiado. Comprueba el estado antes de volver a intentarlo.',
      aborted: 'Se dejó de esperar la respuesta.',
      'invalid-response': 'El servidor devolvió una respuesta inesperada.',
      'csrf-reset': 'La sesión cambió. Vuelve a intentar la operación.',
    };
    super(kind === 'api' && problem ? problem.message : messages[kind as Exclude<ClientErrorKind, 'api'>] ?? 'No se pudo completar la operación.');
    this.name = 'ApiClientError';
    this.kind = kind; this.status = status; this.requestId = requestId; this.problem = problem;
  }
}

export function isUuid(value: unknown): value is string {
  return typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
function text(value: unknown, max: number): value is string {
  return typeof value === 'string' && value.length >= 1 && value.length <= max && /\S/.test(value);
}
function exactKeys(value: Record<string, unknown>, keys: string[]) {
  return Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
}

export function isApiProblem(value: unknown): value is ApiProblem {
  return record(value) && exactKeys(value, ['code', 'message', 'fields', 'request_id'])
    && text(value.code, 80) && /^[A-Z][A-Z0-9_]*$/.test(value.code)
    && text(value.message, 1000) && isUuid(value.request_id)
    && Array.isArray(value.fields) && value.fields.length <= 100
    && value.fields.every(field => record(field) && exactKeys(field, ['path', 'code', 'message'])
      && text(field.path, 200) && text(field.code, 80) && text(field.message, 1000));
}
