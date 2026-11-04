# Compilación y entrega web

SP01-T09, 3 de noviembre de 2026. Django sirve el documento Vue compilado y WhiteNoise entrega sus recursos en el mismo origen que `/api/v1/`. La identidad y el enlace «Apoyar a Jorge» se conservan.

Para instalar desde una copia nueva, seguir primero [Instalación y arranque](instalacion-y-arranque.md), verificada en SP01-T11. Esta guía amplía la etapa de entrega y mantiene la evidencia de T09.

## Preparar y abrir

Con el entorno local y `.env` ya preparados, desde la raíz del repositorio y con el proceso web detenido:

```powershell
.\scripts\preparar-web.ps1
.\scripts\django.ps1 runserver 127.0.0.1:8000 --noreload --nostatic
```

Abrir `http://127.0.0.1:8000/`. `--nostatic` deja la entrega en manos de WhiteNoise también en el servidor local. Como acceso abreviado, después de preparar el build puede ejecutarse `npm run preview` desde `frontend`; ahora inicia este mismo servidor Django mediante PowerShell 7. El servidor local se detiene con Ctrl+C.

El script ejecuta `npm run build`, `scripts/preparar_web.py` y `collectstatic --noinput`. Requiere las versiones de Node, npm, Python y dependencias ya fijadas; no instala paquetes ni requiere servicios de pago. Se ejecutó el flujo completo y una preparación repetida sobre los mismos archivos.

Para editar con recarga de Vue, se mantiene `npm run dev` en `frontend` y Django en 8000 para el proxy, abriendo `http://127.0.0.1:5173/`. Ese modo no necesita volver a compilar para cada edición. El banco de componentes de T08 continúa siendo exclusivo del servidor de desarrollo. Abrir `index.html` como archivo no inicia la aplicación.

## Artefactos y caché

| Ubicación local excluida de Git | Finalidad |
| --- | --- |
| `frontend/dist/index.html` | Documento producido por Vite. |
| `frontend/dist/.vite/manifest.json` | Módulos, imports y recursos del build; no se publica. |
| `.cache/web/index.html` | Copia preparada que lee la vista Django. |
| `.cache/web/versioned-assets.json` | Lista privada de URL versionadas autorizadas para caché inmutable. |
| `.cache/web/static/entrepares` | Recursos públicos de entrada para la colección; incluye las licencias. |
| `.cache/staticfiles` | Salida de `collectstatic`, con variantes gzip cuando reducen el tamaño. |

Los recursos se copian conservando nombres y bytes. La configuración de almacenamiento y su motivo están en [DA02 E02](decisiones/DA02-E02-entrega-web.md). El HTML y los archivos sin versión deben revalidarse; los recursos de la lista de Vite admiten un año de caché inmutable. `index.html` no se puede obtener como un estático alternativo que eluda la política del documento.

Los GET/HEAD del documento proporcionan ETag y pueden responder 304. Un cambio de contenido invalida el ETag anterior. El HTML se comparte entre visitantes y no contiene información privada ni depende de una consulta a la base. Los métodos de mutación no ejecutan acciones en el retorno de navegación; las operaciones funcionales se implementan bajo sus contratos API.

`/api`, `/api/...`, `/admin`, `/admin/...`, `/static` y `/static/...` se reservan antes del retorno HTML. Una API inexistente devuelve 404 JSON con correlación y no-store; un estático ausente devuelve 404 y no recibe la portada. Una ruta de navegación desconocida recibe el documento con 200 para que Vue presente su vista de página no encontrada. Las rutas de archivo con extensión y los segmentos privados que empiezan por punto tampoco reciben el documento. Una petición que solo acepta JSON obtiene 406 en una dirección de navegación; sin build, la navegación obtiene 503 controlado.

Preparar de nuevo requiere detener y reiniciar el proceso web. No se borran automáticamente recursos antiguos: se conserva su disponibilidad para páginas ya abiertas. Esta tarea no cubre despliegue en caliente, limpieza de releases, TLS real ni la configuración del alojamiento definitivo.

## Verificación realizada

Pasaron **188 pruebas del servidor: 169 sin base y 19 con PostgreSQL**, sin fallos ni omisiones, y **68 pruebas del cliente**. Los 35 casos nuevos de servidor cubren navegación, revalidación y cambio de versión, HEAD, métodos, espacios reservados, independencia de API, ausencia de build, negociación, validación de módulos y entrega estática comprimida. Se ajustó el ensayo anterior del límite API para reconocer el nuevo retorno Vue y proporcionarle un documento sintético independiente de la caché local.

Pasaron Ruff, formato de los 96 archivos Python, tipos y compilación Vue de 47 módulos, Django check y `makemigrations --check --dry-run`. La colección inicial copió 44 archivos de las fuentes instaladas y preparadas y produjo 35 variantes comprimidas. De Entrepares se prepararon 17 archivos públicos, 13 de ellos versionados. La preparación repetida conservó los recursos; no es una limpieza de releases.

Un servidor HTTP real de desarrollo con DEBUG desactivado en ese proceso sirvió el HTML, los 13 recursos versionados y sus respuestas condicionales. Se compararon los bytes con Vite; se comprobaron MIME, caché, gzip de CSS, HEAD y exclusión de rutas privadas. Por separado, con ajustes de producción y cliente WSGI de Django se verificaron redirección HTTP a HTTPS, HSTS, HTML y 304, estáticos y error JSON, sin abrir conexión a la base. Esa segunda comprobación no establece una conexión TLS real.

El navegador interno comprobó apertura directa y recarga de `/acerca-de`, navegación y anclas, recarga de la vista desconocida, regreso al inicio, fuentes, imágenes, enlace del pie y menú móvil. Se examinaron 1280 y 390 px sin desbordamiento horizontal y no se observaron errores o advertencias de consola. Se guardaron capturas locales y se restableció el viewport. Los servidores de revisión se cerraron al terminar.

Se conservan nueve tablas, 16 migraciones, cero cuentas sintéticas en desarrollo y dos bases persistentes; la base efímera de pruebas fue eliminada. No cambiaron el esquema, los permisos, las dependencias fijadas, los bloqueos ni las siete fuentes de diseño. El cambio de `package.json` actualiza únicamente el comando de vista previa. Los resultados compactos están en [entrega-web.json](evidencias/entrega-web.json); originales y capturas en `.cache/entrega-web`.

Es evidencia parcial de AT14 y RNF14, relacionada con WI06/WI09. Las 99 operaciones, despliegue Linux, HTTPS/cookies del piloto, rendimiento y evaluación con usuarios conservan su planificación. SP01-T10 automatizará las comprobaciones de estructura y su reproducción desde una copia limpia. SP01 y los trabajos transversales siguen abiertos.
