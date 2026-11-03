# Entrada JSON, errores y parámetros

SP01-T06, 3 de noviembre de 2026. Se prepara la adaptación HTTP del monolito conforme a los contratos de diseño. Las operaciones de negocio se registrarán en sus incrementos; este paso no implementa el registro o el inicio de sesión.

## Rutas y correlación

`config.urls` incluye el espacio `/api/v1/`. Las solicitudes a rutas API desconocidas reciben `404 NOT_FOUND` en JSON, también con `DEBUG=True` y aunque se solicite HTML. El límite comprende `/api` y `/api/...`; las rutas ajenas a ese espacio quedan disponibles para el cliente Vue y los restantes recursos web.

`ApiBoundaryMiddleware` crea un `OperationContext` por solicitud API, antes del resto de middlewares. Todas sus respuestas llevan un UUID de servidor en `X-Request-ID` y `Cache-Control: no-store`. El identificador de una cabecera entrante no se reutiliza como correlación confiable. El mismo contexto queda disponible en `request.operation_context` para el futuro caso de aplicación y su auditoría.

La ruta genérica de recurso ausente no ejecuta mutaciones y conserva su 404 para cualquier método. Las vistas de negocio deben heredar de `JSONAPIView`, declarar sus serializadores y aplicar la autorización correspondiente. La denegación por omisión de SP01-T03 se mantiene.

## Respuesta de error

Todas las respuestas normalizadas tienen exactamente cuatro propiedades:

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Los datos enviados no son válidos.",
  "fields": [
    {"path": "contacts[0].value", "code": "required", "message": "Este campo es requerido."}
  ],
  "request_id": "80ac631c-a0ee-453a-a2aa-d30d85d3b84a"
}
```

El UUID del ejemplo es ficticio. En ejecución `request_id` coincide con `X-Request-ID`. Se mantienen los límites de `ApiError` y `FieldError`: hasta 100 errores, rutas de 200 caracteres, códigos de campo de 80 y mensajes de 1000. El truncamiento conserva valores no vacíos; `$` representa un error general. Los errores de listas usan índices, tanto con el formato de diccionario de DRF 3.18 como con el formato anterior. Se activa `LIST_SERIALIZER_ERRORS_AS_DICT=True` y se normaliza su representación pública.

| Estado HTTP | Códigos preparados |
| --- | --- |
| 400 | `VALIDATION_ERROR` |
| 403 | `AUTH_REQUIRED`, `CREDENTIALS_INVALID`, `CSRF_FAILED`, `FORBIDDEN` |
| 404 | `NOT_FOUND` |
| 405 / 406 | `METHOD_NOT_ALLOWED` / `NOT_ACCEPTABLE` |
| 409 | `STATE_CONFLICT`, `VERSION_CONFLICT` |
| 415 | `UNSUPPORTED_MEDIA_TYPE` |
| 429 | `THROTTLED` |
| 500 | `INTERNAL_ERROR` |
| 503 | `POLICY_NOT_CONFIGURED`, `SERVICE_UNAVAILABLE` |

Las credenciales y la ausencia de sesión usan 403 sin reto `WWW-Authenticate`, conforme a la autenticación por sesión. `Retry-After` se conserva cuando la excepción de límite proporciona un plazo. Preparar un código no activa por sí mismo una política o una función; el caso debe decidir su aplicabilidad.

`ApiProblem` admite códigos del catálogo con mensajes controlados. Las excepciones internas se convierten en un mensaje genérico. El límite de Django normaliza también errores de vistas comunes y fallos al renderizar una respuesta, conservando JSON en ambos modos de depuración. Las respuestas de error sin formato propio se reconstruyen con cabeceras de seguridad y de protocolo seleccionadas; no se copian metadatos obsoletos del cuerpo ni cabeceras internas arbitrarias.

El logger `entrepares.api` registra la clase de excepción y la correlación, visibles también en el mensaje de texto. No registra el mensaje interno de la excepción, su traza, cuerpo o cabeceras. Los mensajes de validación declarados por los serializadores deben seguir siendo aptos para mostrarse al usuario y no contener secretos.

Los códigos de transporte 405, 406, 415 y disponibilidad complementan la lista general `x-error-codes` del diseño. El esquema `ApiError` ya admite sus códigos estables; la concreción está en [DA02 E01](decisiones/DA02-E01-entrada-json.md). Las fuentes históricas de diseño conservan sus huellas.

## Cuerpo JSON y serializadores

`StrictJSONParser` limita los parsers de entrada a `application/json`. Rechaza sintaxis inválida, claves duplicadas, números no finitos y errores de decodificación o profundidad sin mostrar detalles del parser. Los valores repetidos dentro de un array siguen siendo válidos; la restricción afecta a claves duplicadas de un objeto.

`JSONSerializer` rechaza propiedades inesperadas, de solo lectura o reservadas como `HiddenField`. Debe utilizarse también en objetos anidados. Los tipos, campos obligatorios, formatos, longitudes, colecciones y reglas particulares se declaran por operación conforme al esquema; este incremento no traslada los 116 esquemas a serializadores funcionales ni sustituye la autorización de `application`.

`JSONAPIView` valida siempre los parámetros declarados y, para métodos no seguros, el cuerpo mediante `input_serializer_class`. Por omisión usa un objeto de entrada vacío: una operación sin campos no acepta propiedades adicionales. Los resultados están en `validated_query` y `validated_input`. Un endpoint con datos debe declarar explícitamente sus clases de entrada.

## Consulta y paginación

`QuerySerializer` rechaza parámetros desconocidos y repeticiones de un parámetro escalar. Los filtros adicionales se declaran en una subclase según el contrato y su condición funcional; su mera existencia en OpenAPI no activa una opción pendiente.

`PageQuerySerializer` valida `page`, con mínimo 1 y valor inicial 1, y `page_size`, de 1 a 100 con valor inicial 20. Los enteros de consulta usan dígitos, sin coerción de decimales o booleanos; los filtros `QueryBooleanField` aceptan los textos `true` o `false`. Un límite excesivo se rechaza con 400, sin reducirlo silenciosamente.

`ContractPagination` consume los parámetros ya validados y devuelve exactamente `count`, `page`, `page_size` y `results`. Una página fuera del rango del conjunto produce `400 VALIDATION_ERROR` en `page`. Una colección vacía admite su primera página con cero resultados. El propietario define la consulta y un orden estable antes de paginar; el paginador no construye filtros de negocio ni consultas entre propietarios.

## CSRF y sesión

Antes de procesar una operación, `JSONAPIView` ejecuta la comprobación CSRF de Django también para participantes sin sesión. Se mantienen `SessionAuthentication`, las cookies y las comprobaciones de origen y referente de Django. `CSRF_FAILURE_VIEW` normaliza los rechazos de vistas Django dentro de API.

Las pruebas usan `Client(enforce_csrf_checks=True)`: una mutación sin token falla, un token válido permite pasar al handler autorizado, y un origen ajeno o un token anterior a una rotación se rechazan. Una sesión real de Django sigue necesitando CSRF; la cuenta deshabilitada técnicamente pierde el acceso privado aunque conserve su cookie. Esto no equipara una deshabilitación técnica con una medida de moderación del producto.

Las rutas de emisión de token y rotación usadas para el ensayo son sintéticas y están únicamente en el URLConf de pruebas. API001 y las operaciones de sesión mantienen su implementación planificada en SP03-T03; no se publican rutas ficticias bajo `/api/v1/`.

## Evidencia y límites

```powershell
.\scripts\probar.ps1 -Modo todas -q
.\.venv\Scripts\python.exe -m pytest backend/api/tests -q
.\.venv\Scripts\ruff.exe check backend scripts
```

Se usa el servidor Django completo del cliente de pruebas y PostgreSQL para la sesión persistida. Se comprobó además una petición HTTP real mediante un servidor WSGI temporal en loopback, con ajustes de desarrollo: una ruta inexistente devolvió 404 JSON, correlación de servidor y `no-store` aun con `DEBUG=True`. El servidor temporal se cerró al terminar.

Esta es evidencia parcial de AT14 y del transporte relacionado con CT12. No acredita recarga de Vue, HTTPS del piloto, operaciones de negocio, límites de abuso ya activos, el conjunto completo de contratos ni el despliegue Linux. No modifica esquema o dependencias. Los resultados están en [entrada-json.json](evidencias/entrada-json.json).

## Referencias

- OpenAPI de diseño y registro de operaciones, identificados en [Base documental](base-documental.json).
- [Excepciones y adaptación de respuestas de DRF](https://www.django-rest-framework.org/api-guide/exceptions/).
- [Autenticación por sesión y CSRF de operaciones sin sesión](https://www.django-rest-framework.org/api-guide/authentication/#sessionauthentication).
- [Notas de DRF 3.18](https://www.django-rest-framework.org/community/release-notes/#3180).
- [Protección CSRF y solicitudes AJAX en Django 5.2](https://docs.djangoproject.com/en/5.2/howto/csrf/).
