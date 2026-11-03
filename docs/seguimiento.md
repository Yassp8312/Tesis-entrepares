# Seguimiento de implementación

## 30 de octubre de 2026

SP01-T01 prepara el repositorio y sus ubicaciones iniciales: cliente, servidor, documentación, configuración y diez módulos internos con responsabilidad identificada. Se incorporan exclusiones de secretos y datos locales, convenciones de formato y reglas de arquitectura.

Se comprobó la correspondencia de los diez módulos con el registro de arquitectura, la sintaxis de los paquetes Python y la identificación de siete fuentes mediante SHA256. Git excluyó las 18 rutas representativas de archivos privados o generados examinadas y conservó las diez rutas de código, migraciones, ejemplos y dependencias examinadas. La rama inicial es `main`, sin remotos configurados. Estas comprobaciones de preparación se registran en `evidencias/repositorio-inicial.json`; los escenarios AT01 y AT18 del producto todavía no se han ejecutado sobre una aplicación.

Los estados de los documentos de planificación conservan su versión de diseño. Este registro identifica el avance de implementación posterior; cerrar SP01-T01 no termina WI06 ni el sprint SP01.

## Siguiente trabajo

SP01-T02 se completó con Python 3.13.17, Django 5.2.18, DRF 3.18.3, Node 24.18.0 y las dependencias Vue fijadas. `uv.lock` y `frontend/package-lock.json` permiten reproducir las versiones. Se preparó el script Windows `scripts/preparar-entorno.ps1`, con descarga de uv verificada por SHA256, Python local sin registro global, instalación bloqueada y comprobaciones técnicas.

Se ejecutó el script completo y se repitió la instalación en una carpeta independiente con un entorno virtual y un `node_modules` nuevos. Coincidieron los 16 paquetes Python instalados y las huellas de ambos bloqueos; funcionaron los imports, los ajustes sintéticos de Django, el adaptador PostgreSQL, el análisis Ruff, los tipos Vue/TypeScript, una compilación Vite y una ruta en memoria. No se abrió una conexión a la base ni se aplicaron migraciones.

La referencia DRF 3.16 se ajustó mediante [DA03 E01](decisiones/DA03-E01-dependencias.md): la auditoría inicial encontró siete registros equivalentes a cinco avisos; el corte final con 3.18.3 no presentó avisos en uv ni npm. Estas consultas no certifican la seguridad del producto. La evidencia compacta está en `evidencias/dependencias.json`; los originales de QA permanecen fuera de los archivos versionados del producto.

## 2 de noviembre de 2026

SP01-T03 incorpora `manage.py`, ajustes separados de desarrollo, prueba y producción, WSGI, configuración local excluida de Git y el modelo `identity.Account` con su primera migración. Mantiene las nueve columnas T01, los dos CHECK y la unicidad funcional del correo. La autenticación reutiliza Django y las operaciones HTTP sin permisos explícitos se deniegan por omisión.

Pasaron 35 pruebas sin acceso a una base, Ruff y los chequeos de Django. La migración coincide con los modelos y sustituye `auth.User` en su grafo. Las pruebas incluyen contraseñas reales codificadas, reglas de creación, búsqueda y autenticación sintéticas, rechazo de configuraciones de producción incompletas y denegación de una vista no configurada a un superusuario técnico. La evidencia está en `evidencias/configuracion-y-cuenta.json` y la decisión técnica en [DA04 E01](decisiones/DA04-E01-cuenta-y-configuracion.md). El aviso genérico `auth.W004` se sustituye por un control específico del índice funcional; la salida de `check` refleja un aviso silenciado.

El siguiente trabajo es **SP01-T04**, preparar PostgreSQL de desarrollo y prueba y aplicar las migraciones sobre una base vacía. Se deben comprobar allí los duplicados por mayúsculas y las restricciones reales. El servicio existente y sus datos no se han intervenido; no se abrió una conexión ni se aplicó SQL en T03. SP01-T05 prepara contratos y reloj técnicos; SP01-T07 puede preparar Vue. El sprint SP01 y WI06 siguen abiertos.

### PostgreSQL y pruebas de integración: SP01-T04

Se completó la preparación de PostgreSQL 17.11 para Windows en `.tools/postgresql/17.11`, escuchando solo en `127.0.0.1:55432`, sin utilizar la instalación 17.5 existente ni crear un servicio de Windows. La distribución exacta queda fijada por URL, tamaño y SHA256. Los scripts preparan el cluster UTF-8/ICU, generan credenciales locales y separan los roles y las bases de desarrollo y pruebas. Los datos, registros y secretos permanecen excluidos de Git.

Se comprobó que `entrepares_development` no contenía tablas antes de aplicar las 16 migraciones de Django. El esquema resultante tiene nueve tablas, incluida T01 `identity_account` con sus nueve columnas, índice único funcional y dos CHECK; no se creó `auth_user`. Solo T01 corresponde al modelo de negocio implementado hasta aquí. Las otras tablas son infraestructura de autenticación, sesiones y migraciones.

Pasaron **47 pruebas en 32,65 s: 35 sin base y 12 de integración con PostgreSQL real**. Se comprobaron guardado, hash, UUID, fechas, búsqueda de correo, rechazo de duplicados por mayúsculas, restricciones mediante SQL, valores predeterminados de base, autenticación, sesiones y separación de acceso entre bases. La base efímera `test_entrepares` se eliminó al terminar y la base de desarrollo quedó sin cuentas de prueba. Un ensayo adicional con una etiqueta de servidor deliberadamente incorrecta fue rechazado antes de crear la base efímera, conservando las bases y los registros de desarrollo.

Se ensayaron repetición de `preparar`, parada y arranque del cluster y repetición de `migrate`: se conservaron `.env`, credenciales, esquema y recuentos; no quedaron migraciones pendientes. El ajuste de los comandos nativos usa un archivo de registro para evitar que las tuberías heredadas del servidor mantengan bloqueado `pg_ctl` en Windows. Pasaron los chequeos de Django sobre la base y la comprobación de ausencia de diferencias entre modelos y migraciones. La evidencia está en [postgresql-local.json](evidencias/postgresql-local.json) y los comandos en [PostgreSQL local](postgresql-local.md).

El siguiente trabajo es **SP01-T05: contratos y reloj técnicos**. El cliente Vue sigue pendiente de SP01-T07 y no hay todavía pantallas del producto. El sprint SP01 y WI06 siguen abiertos; estos resultados no corresponden a pruebas de endpoints, concurrencia del producto ni evaluación del piloto.

### Interfaces propietarias y reloj técnico: SP01-T05

Cierre el 3 de noviembre de 2026. Se delimitaron los paquetes `commands`, `selectors` y `contracts` en los diez propietarios. M01 tiene una primitiva de creación ordinaria y un selector de estado actual de cuenta que devuelven el DTO inmutable `AccountState`, limitado a UUID y habilitación técnica. Los nueve módulos restantes tienen sus interfaces reservadas para incorporar las funciones durante sus incrementos. El registro completo y sus efectos coordinados siguen pendientes de sus casos de aplicación.

`core` incorpora `Clock`, `SystemClock`, `FixedClock`, normalización de instantes conscientes de zona a UTC, UUID v4 y un contexto de operación con correlación y reloj explícitos. El contexto vuelve a consultar el tiempo al solicitarlo; no congela una autorización al entrar en la solicitud. No se alteran fechas automáticas del modelo o de PostgreSQL ni se resuelven las políticas Q03/Q08. Los límites y fuentes se explican en [Contratos internos y reloj](contratos-y-reloj.md) y la decisión [DA05 E01](decisiones/DA05-E01-contratos-y-tiempo.md).

Pasaron **81 pruebas en 49,24 s: 64 sin base y 17 con PostgreSQL**, sin fallos ni omisiones. Se incorporaron 29 pruebas sin base de reloj, correlación y límites estáticos, y cinco de integración de las interfaces M01. Se verifican valores temporales y rechazo de instantes ambiguos, UUID y contextos independientes, interfaces de los diez propietarios, importaciones reales y ejemplos inyectados, DTO mínimo, estado actual en una consulta, validadores y rollback de la primitiva ante fallo externo. El control AST rechaza HTTP/application en negocio y modelos ajenos; permite `application` en la entrada CLI autorizada. Es evidencia parcial de AT01, no una demostración de todas las escrituras ni ejecución del futuro caso AT09.

Pasaron Ruff, formato de los 81 archivos Python, chequeo de Django con la base y ausencia de diferencias entre modelos y migraciones. Se verificaron las siete huellas de fuentes de diseño; permanecen sin cambios. El esquema conserva nueve tablas y 16 migraciones, sin cuentas de pruebas en desarrollo, y la base efímera fue eliminada. La evidencia compacta está en [contratos-y-reloj.json](evidencias/contratos-y-reloj.json).

El siguiente trabajo es **SP01-T06: entrada JSON y errores**, con `/api/v1/`, correlación en errores, validación y paginación conforme a OpenAPI. SP01, WI06 y WI08 permanecen abiertos; este incremento no incorpora aún pantallas ni resultados del piloto.

### Entrada JSON y controles HTTP: SP01-T06

Cierre el 3 de noviembre de 2026. Se reservó `/api/v1/` y se incorporaron middleware de límite JSON y correlación, manejador de errores, parser JSON, serializadores cerrados, parámetros escalares y paginación. Las rutas API desconocidas devuelven 404 JSON incluso con DEBUG activo o Accept HTML; todas las respuestas API llevan correlación de servidor y no-store. Se conserva el origen común y la denegación por omisión.

`JSONAPIView` exige CSRF de Django también sin sesión y valida consulta y cuerpo declarados. Los objetos rechazan propiedades inesperadas o reservadas y la consulta rechaza repeticiones. La paginación usa 1/20, máximo 100, y devuelve las cuatro propiedades del contrato. Se normalizan errores anidados con índices para los formatos nuevo y anterior de listas DRF; los fallos internos tienen mensaje controlado y registro propio con UUID y clase. [DA02 E01](decisiones/DA02-E01-entrada-json.md) concreta los códigos de transporte y las convenciones de rango y cabeceras sin modificar las fuentes de diseño.

Pasaron **153 pruebas en 37,83 s: 134 sin base y 19 de integración PostgreSQL**, sin fallos ni omisiones. T06 incorpora 70 pruebas de transporte y dos de sesión persistida. Los casos usan el cliente Django con CSRF activado y cubren campos, JSON ambiguo, consulta, paginación, permisos, método, negociación, cabeceras, origen, referente HTTPS, rotación de CSRF, sesiones, deshabilitación técnica y fallos de renderizado. Las rutas sintéticas existen únicamente en el URLConf de pruebas. El arranque CSRF API001 y las operaciones de sesión siguen planificados en SP03-T03.

Se comprobó una petición HTTP real en loopback mediante WSGI temporal de desarrollo: 404 JSON con UUID y no-store frente a Accept HTML y un identificador de cliente no confiable. Se contrastaron sus propiedades y límites con ApiError fuente y se cerró el servidor temporal. Pasaron Ruff y formato de 92 archivos Python, Django check con base y makemigrations sin cambios. Las siete fuentes conservan sus huellas; se mantienen nueve tablas y 16 migraciones, cero cuentas sintéticas en desarrollo y dos bases persistentes tras eliminar la base efímera.

La evidencia está en [entrada-json.json](evidencias/entrada-json.json) y los comandos y límites en [Entrada JSON](entrada-json.md). Es evidencia parcial de AT14 y del transporte relacionado con CT12; no acredita Vue, HTTPS de piloto, límites de abuso activos o validación funcional de los 99 contratos.

El siguiente trabajo es **SP01-T07: crear Vue y cliente HTTP común**, con TypeScript, Vue Router, proxy local y tratamiento de errores y CSRF. La identidad visual se incorpora con sus recursos acordados y el enlace discreto a Apoyar a Jorge. SP01 y WI06 permanecen abiertos.

### Cliente Vue y transporte común: SP01-T07

Cierre el 3 de noviembre de 2026. Se incorporó Vue con TypeScript, navegación HTML5, portada, presentación y página no encontrada. La interfaz integra inicialmente los recursos de la propuesta de marca v1 y conserva el estado real del desarrollo; no presenta contactos, proyectos o resultados ficticios. Doce recursos se contrastaron con el manifiesto y las licencias acompañan también a la compilación. La biblioteca completa de componentes de SP01-T08 sigue pendiente.

El transporte común mantiene el origen, las cookies de sesión y un contexto organizacional explícito, valida errores y correlación, limita rutas a API y no sigue redirecciones. CSRF se conserva en memoria, con obtención compartida, actualización/reset y cancelación de espera sin afectar a otros participantes. No hay reintentos automáticos de mutaciones. Vite no carga dotenv ni expone variables personalizadas del proceso; el proxy local conserva Host y Origin y reserva api/admin/static al servidor.

Pasaron **37 pruebas del cliente**, sin fallos ni omisiones, y los chequeos de tipos y compilación. Se verificó el cliente frente a Vite y Django reales: reconoce el 404 del servidor y, si el bootstrap CSRF no existe, no llega a enviar el POST. API001 y la sesión siguen en SP03-T03. El backend y los bloqueos de dependencias no cambiaron; sus 153 pruebas previas se conservan como evidencia de T06, sin atribuirles una ejecución nueva.

La revisión en navegador comprobó navegación, recarga, página no encontrada, menú por teclado, Escape, foco, salto al contenido y el enlace del pie. Se examinaron anchos de 1413, 1280, 390 y 320 px sin desbordamiento horizontal; también se verificó la compilación mediante Vite preview. Las fuentes e imágenes cargaron localmente y no hubo errores o advertencias de consola en los recorridos observados. Se corrigió el cierre del menú al seleccionar la página actual. Las capturas quedan en `.cache/vue-http` y el tamaño temporal del navegador se restableció.

La compilación no contiene los secretos conocidos del proyecto ni configuración privada de servidor. Las siete fuentes de diseño conservan sus huellas. Los servidores HTTP utilizados para la revisión se cerraron al terminar y el PostgreSQL privado se conserva activo. La guía está en [Cliente Vue](cliente-vue.md), con evidencia en [cliente-vue.json](evidencias/cliente-vue.json) y [recursos iniciales](evidencias/recursos-marca-iniciales.json). Es evidencia parcial de AT14/AT18; siguen pendientes collectstatic y retorno Django, despliegue y piloto.

El siguiente trabajo es **SP01-T08: integrar recursos de marca y componentes comunes**, completando botones, campos, estados, diálogo y avisos con su comprobación de foco, etiquetas, contraste y adaptación. SP01 y WI06 permanecen abiertos.

### Componentes visuales comunes: SP01-T08

Cierre el 3 de noviembre de 2026. Se incorporaron botones de acción, enlaces de navegación, campos de texto/área/selección con contenedor de etiqueta, estados, avisos y diálogo modal. Los estilos reutilizan la propuesta de marca v1; el icono común admite los 24 nombres del sprite local. La portada y la página no encontrada usan el enlace común y la presentación incorpora el aviso estático. El pie conserva «Apoyar a Jorge». No se añadieron dependencias ni funciones de negocio.

Los campos relacionan etiqueta, ayuda y error, preservan atributos nativos y exponen foco. Carga y deshabilitación impiden activar botones. Los estados siempre tienen texto y los anuncios de avisos son explícitos. El diálogo nativo recibe foco en el título y lo devuelve al control de apertura conectado al cerrar o desmontar. Una revisión detectó salida de foco al tabular en los extremos; se añadió contención explícita y se repitió el recorrido correctamente.

Pasaron **67 pruebas del cliente: 37 existentes, 15 de estructura de componentes y 15 de contraste**, sin fallos ni omisiones. Los chequeos de tipos y compilación pasaron; Vite transformó 47 módulos. Las pruebas estructurales usan Vue SSR mediante Vite sin instalar librerías adicionales. Los pares examinados alcanzan 4,5:1 para texto y 3:1 para bordes. El backend no cambió y no se repitieron sus 153 pruebas de T06.

El banco sintético de `tests/fixtures` queda fuera del router y de la compilación de producción. Se comprobó en el navegador la activación, carga, edición y selección, error y foco, cierre de aviso, diálogo, Tab/Mayús+Tab, Escape, cierre explícito, confirmación, cierre desde el padre y desmontaje. Se revisaron 1280, 390 y 320 px sin desbordamiento horizontal, campos/botones regulares de 48 px y controles de cierre de 44 px. La compilación se examinó con Vite preview para los enlaces comunes y el aviso integrado. No se observaron errores o advertencias de consola; se restableció el tamaño del navegador.

Se verificaron las siete fuentes de diseño y los doce recursos de marca sin cambios, licencias en la compilación y ausencia de secretos conocidos en el cambio y los archivos compilados. Registros, capturas y JUnit quedan en `.cache/componentes`, excluidos de Git. Se cerraron los servidores Vite y preview tras comprobar sus procesos propios; se conserva PostgreSQL privado. La guía es [Componentes visuales](componentes-visuales.md), con evidencia en [componentes-visuales.json](evidencias/componentes-visuales.json).

Es evidencia técnica parcial de **AT16**, relacionada con WI06/WI30, DV03/DV06 y RNF07/RNF08/RNF11. La evaluación con usuarios, las tareas U01–U08, lectores de pantalla, compatibilidad completa y conformidad WCAG global siguen pendientes. El siguiente trabajo es **SP01-T09: compilación, collectstatic y retorno de navegación Django**, excluyendo `/api/`, `/admin/` y `/static/`. SP01, WI06 y WI30 permanecen abiertos.
