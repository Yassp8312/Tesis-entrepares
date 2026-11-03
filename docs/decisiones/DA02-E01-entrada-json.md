# DA02 E01 Límite JSON y validación de transporte

Fecha: 3 de noviembre de 2026. Concreción de DA02, DA04 y SP01-T06, y de la adaptación de errores indicada en DA03 E01.

## Decisión

Reservar `/api/v1/` para las operaciones e impedir que sus errores o rutas desconocidas se conviertan en HTML de navegación o depuración. La correlación se genera en el servidor y se comparte con la futura capa de aplicación. Se usa `ApiError`, sus cuatro propiedades y las cabeceras del contrato.

Normalizar listas de validación independientemente del formato interno de DRF. Se activa el formato de diccionario de 3.18 y se prueba también la adaptación del formato anterior, conservando índices y rutas de campo. Los errores internos usan mensajes controlados y un registro técnico con clase y UUID, sin publicar la excepción.

La entrada JSON rechaza claves duplicadas y números no finitos. Los objetos se validan mediante serializadores cerrados y los parámetros escalares no se repiten. La paginación conserva sus valores 1/20 y máximo 100; un valor inválido o una página fuera del conjunto produce 400. Esta convención concreta un límite de transporte sin añadir políticas de negocio.

La base de vistas exige CSRF explícito incluso sin sesión y mantiene la autenticación de sesión existente. El 404 genérico no ejecuta mutaciones. Las futuras vistas de negocio heredan de `JSONAPIView` y declaran entradas y autorización. Los endpoints funcionales, incluida la emisión del token CSRF API001, se implementan en sus tareas.

## Concreción del catálogo

La lista general `x-error-codes` del diseño no enumera todas las condiciones HTTP: ya se documentan una respuesta 415 y credenciales inválidas en Error403, y 503 admite dependencia temporalmente indisponible. Se preparan `UNSUPPORTED_MEDIA_TYPE`, `CREDENTIALS_INVALID` y `SERVICE_UNAVAILABLE`. `METHOD_NOT_ALLOWED` y `NOT_ACCEPTABLE` representan 405 y 406 del protocolo. Todos mantienen la estructura y patrón de `ApiError`. No se altera el documento original ni se declara implementada una operación por incluir un código.

Al reconstruir un error ordinario de Django se conserva una lista explícita de cabeceras de seguridad y protocolo. Una respuesta 401 ordinaria se normaliza a 403 de sesión; estados sin correspondencia producen un error interno controlado. Se evita copiar cabeceras internas o metadatos de un cuerpo sustituido.

## Comprobación

Pruebas de resolver y middleware en ambos modos DEBUG, entrada JSON y campos reservados, listas de errores, filtros y paginación, CSRF anónimo, origen, rotación, sesión real en PostgreSQL y fallo de renderizado. Se añade un ensayo HTTP en loopback. Los límites de AT14/CT12 y las fuentes técnicas están en [Entrada JSON](../entrada-json.md); no se acredita todavía interfaz Vue, piloto ni validación funcional de las 99 operaciones.
