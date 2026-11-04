# Cliente Vue y solicitudes comunes

SP01-T07, 3 de noviembre de 2026. Aplicación Vue 3 y TypeScript con navegación HTML5, cliente HTTP y proxy local al servidor Django. Se conservan las dependencias fijadas y el monolito modular.

## Ejecutar localmente

Con el entorno y las bases de SP01-T04 preparados, desde la raíz del repositorio:

```powershell
.\.venv\Scripts\python.exe scripts\postgresql_local.py iniciar
.\scripts\django.ps1 runserver 127.0.0.1:8000 --noreload
```

En otra terminal, dentro de `frontend`:

```powershell
npm run dev
```

Abrir `http://127.0.0.1:5173/`. Ambos servidores se detienen con Ctrl+C en su terminal. Los puertos son estrictos para evitar que se seleccione otro origen silenciosamente. Si el servidor Django usa otro puerto, configurar `ENTREPARES_API_TARGET` en el proceso que ejecuta Vite, por ejemplo `http://127.0.0.1:8010`. El valor debe ser un origen de loopback HTTP/HTTPS, sin credenciales, ruta, consulta ni fragmento.

Vite no carga archivos dotenv (`envDir: false`) ni expone variables personalizadas del proceso al cliente (`envPrefix: []`); la configuración privada Django permanece en la raíz y la carga su script propio. El destino del proxy es configuración del servidor de desarrollo y no se inyecta en componentes o bundles. El cliente solicita rutas relativas. El proxy conserva Host y Origin (`changeOrigin: false`) para las comprobaciones del origen común y reserva `/api`, `/admin` y `/static` al servidor. Una ruta API inexistente no recibe el documento Vue.

## Interfaz y navegación

Hay una portada, la presentación `/acerca-de` con anclas de las tres partes del producto y una vista de página no encontrada. Vue Router gestiona enlaces, título y posición de navegación. Se verificó la recarga directa de una ruta interna en Vite. El retorno de navegación del despliegue Django se preparará en SP01-T09.

La portada utiliza logo, símbolo, colores, fuentes e iconos de la propuesta visual v1. No contiene personas, proyectos, cifras, respaldos o resultados de investigación ficticios. Explica la propuesta y su estado de preparación; las funciones de perfiles, registro, oportunidades y divulgación siguen pendientes de sus incrementos.

El menú móvil expone `aria-expanded`, se cierra al elegir una página, incluso si ya era la actual, y admite Escape. La navegación lleva el foco al contenido sin alterar la posición del ancla. Hay salto al contenido, foco visible y adaptación a movimiento reducido. El pie conserva «Apoyar a Jorge» como enlace externo discreto con `noopener noreferrer`.

Los 12 recursos iniciales se contrastaron con el manifiesto de identidad. Las fuentes son locales y las licencias quedan en `frontend/public/licenses`, incluidas también en `dist/licenses` al compilar. Git conserva sus bytes originales, incluidos espacios y finales de línea; esa excepción de formato se limita al directorio de licencias. El CSS de tokens se normaliza a LF y registra por separado la huella de fuente y la de la copia. La procedencia y las huellas están en [recursos-marca-iniciales.json](evidencias/recursos-marca-iniciales.json). La biblioteca completa de componentes y la aprobación visual final siguen pendientes de SP01-T08 y de la revisión correspondiente; no se alteran las fuentes históricas.

## Cliente HTTP

`src/api/client.ts` ofrece `createApiClient()` y una instancia común `api`. `request(path, options)` recibe una ruta relativa, por ejemplo `opportunities/`, y la resuelve bajo `/api/v1/`. Rechaza destinos externos, segmentos de recorrido, separadores o fragmentos introducidos en la ruta. Los filtros viajan por `query` mediante `URLSearchParams`; se conservan `false` y cero, y se omiten valores `undefined`.

Las solicitudes usan `credentials: same-origin`, `mode: same-origin`, `cache: no-store` y `redirect: error`. El cuerpo declarado se serializa como JSON y rechaza números no finitos. El llamador no puede sustituir esas opciones por credenciales, destinos o cabeceras arbitrarias. `organizationId` admite un UUID y añade `X-Organization-ID` explícito; una denegación no retira ese contexto ni reintenta en nombre personal.

Los resultados correctos son `unknown`, para exigir la validación de la proyección en cada funcionalidad. Una respuesta 204 o HEAD correcto devuelve `undefined`. Las respuestas JSON exigen una correlación válida de servidor. `ApiClientError` diferencia problemas públicos de API, fallo de red, plazo agotado, cancelación, respuesta inesperada y cambio de la comprobación CSRF. Los errores públicos se validan conforme a la forma y límites de `ApiError` y `FieldError`, y su UUID debe coincidir con la cabecera.

Los errores HTML, JSON mal formado, esquemas inesperados o mensajes internos de la red no se convierten en contenido para la interfaz. No se registran cuerpos, contraseñas ni tokens en consola. Las solicitudes admiten `AbortSignal` y un plazo de 30 segundos por omisión, incluyendo la espera de CSRF. Cancelar la espera o perder la conexión no garantiza que el servidor haya revertido una operación ya recibida. No hay reintentos automáticos de mutaciones; el estado debe consultarse antes de repetir una acción cuyo resultado no se conoce.

## Ciclo CSRF

Antes de un método no seguro, el cliente obtiene el token enmascarado de `auth/csrf/` y lo conserva solo en memoria. Las mutaciones concurrentes comparten esa obtención. Cancelar una de ellas no cancela la comprobación que otra está esperando. `resetCsrf()` impide que una obtención anterior repueble la caché después de un cambio de sesión.

El adaptador funcional de login deberá aplicar `setCsrfToken(session.csrf_token)` con la respuesta validada del contrato. Logout o cambios que invaliden la sesión descartan la caché mediante `resetCsrf()`. Ante `CSRF_FAILED` también se descarta el token, sin repetir la mutación. No se usan localStorage o sessionStorage para credenciales ni se lee el valor de la cookie CSRF desde JavaScript.

API001 sigue planificada en SP03-T03 y ahora devuelve 404 real. Se comprobó que ese resultado impide enviar el POST, sin fabricar un token o simular un registro. La portada no inicia una comprobación que todavía no está disponible. Las pruebas de respuestas CSRF correctas usan transportes sintéticos identificados; la integración funcional con login se comprobará cuando exista ese endpoint.

## Comprobaciones

Desde `frontend`:

```powershell
npm run typecheck
npm test
npm run build
```

Las pruebas usan el ejecutor nativo de Node y las dependencias ya fijadas. Cubren rutas, configuración del proxy, opciones del transporte, filtros, errores, CSRF concurrente y renovado, reset durante una obtención, cancelación, plazo y ausencia de reintentos. El JUnit de esta ejecución queda fuera de Git en `.cache/vue-http` de la raíz.

Se verificó además el cliente común frente al proxy Vite y al Django real para el 404 y la ausencia de bootstrap CSRF; y se revisó en el navegador la portada, presentación, recarga, página no encontrada, menú, teclado y foco. Las vistas de inicio se examinaron a 1413, 1280, 390 y 320 píxeles de ancho sin desbordamiento horizontal; la compilación también se revisó mediante Vite preview. Se conservaron capturas locales de escritorio y móvil y se restableció el tamaño del navegador. No hubo errores o advertencias de consola en los recorridos observados.

Los resultados están en [cliente-vue.json](evidencias/cliente-vue.json). Son evidencia parcial de AT14/AT18: no acreditan el despliegue Linux, HTTPS del piloto, todas las rutas, compatibilidad exhaustiva, conformidad WCAG completa ni permisos del producto. Las fuentes locales ocupan aproximadamente 1,08 MB antes de compresión; el rendimiento con conectividad del piloto se evaluará en sus tareas.

## Referencias

Actualización posterior: SP01-T08 completa los componentes comunes descritos en [Componentes visuales](componentes-visuales.md). Los resultados de T07 anteriores conservan su fecha y alcance; la evidencia del nuevo incremento se registra por separado.

SP01-T09 incorpora la [entrega compilada con Django](entrega-web.md), el manifiesto de Vite y los recursos bajo `/static/entrepares/`. `npm run preview` inicia ahora Django después de preparar los artefactos; Vite de desarrollo conserva su base `/` y el proxy local.

- Plan SP01-T07, arquitectura y contratos identificados en [Base documental](base-documental.json).
- [Proxy y opciones de servidor de Vite](https://vite.dev/config/server-options#server-proxy).
- [Navegación HTML5 de Vue Router](https://router.vuejs.org/guide/essentials/history-mode.html).
- [Cookies, errores y cancelación con Fetch](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch).
