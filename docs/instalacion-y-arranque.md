# Instalación y arranque local

Guía de SP01-T11, 4 de noviembre de 2026. Describe el entorno de desarrollo de Entrepares en Windows x64. Todas las órdenes se ejecutan desde la raíz del repositorio salvo cuando se indica otra carpeta.

## Requisitos

- PowerShell 7 (`pwsh`), Node 24.18.0 y npm 11.16.0 disponibles en PATH.
- Una copia de las fuentes y espacio para dependencias, cachés y PostgreSQL privados.
- Acceso a los repositorios de descargas durante la preparación, o los artefactos ya verificados en sus cachés.

Comprobar las herramientas:

```powershell
$PSVersionTable.PSVersion
node --version
npm --version
```

Los scripts instalan Python 3.13.17 y uv 0.13.6 localmente. No requieren activar `.venv`, instalar Python globalmente, Docker ni servicios de pago. Las dependencias se fijan en [Entorno](entorno.md) y los binarios PostgreSQL en `scripts/postgresql-runtime.json`. El aprovisionamiento descrito está comprobado en Windows; las instrucciones Linux anteriores son orientativas y su arranque se verificará en el despliegue correspondiente.

## Primera instalación

Ejecutar en este orden, comprobando que termine cada paso:

```powershell
.\scripts\preparar-entorno.ps1
.\scripts\preparar-configuracion.ps1
.\.venv\Scripts\python.exe scripts\postgresql_local.py preparar
.\scripts\preparar-web.ps1
.\scripts\django.ps1 migrate --noinput
.\scripts\django.ps1 check --database default --fail-level WARNING
```

La preparación del entorno descarga uv con SHA256 fijada, crea Python y `.venv` dentro del proyecto e instala desde `uv.lock` y `frontend/package-lock.json`. npm utiliza `.tools/npm-cache`. No cambia Node globalmente.

La configuración genera una clave Django aleatoria en `.env`; repetir ese comando conserva el archivo existente. `.env.example` es una referencia de campos, con secretos vacíos, no una configuración operativa para copiar sobre otra instalación. Después, PostgreSQL genera sus propias credenciales y completa las variables de desarrollo y pruebas.

La configuración inicial contiene el puerto provisional 5432. No se usa para arrancar la aplicación en esta secuencia: `postgresql_local.py preparar` lo sustituye por el puerto de su cluster, 55432 por omisión. Si ese puerto ya está ocupado, **antes de crear el cluster** sustituir el tercer paso por:

```powershell
.\.venv\Scripts\python.exe scripts\postgresql_local.py preparar --port 55433
```

Un cluster ya preparado conserva su puerto. Sus bases y roles se crean dentro de ese servidor privado, aunque sus nombres coincidan con los de otra copia. Cada copia necesita su propia configuración y credenciales; no copiar el `.env` ni el directorio de datos de otra instalación.

Se prepara la interfaz antes de migrar y comprobar Django para que existan sus directorios estáticos. `preparar-web.ps1` compila Vue, separa el documento HTML de los recursos públicos y ejecuta `collectstatic`. `migrate` aplica exclusivamente las migraciones implementadas: actualmente T01 y la infraestructura Django. No se ejecuta el SQL completo del diseño de las 37 tablas de negocio. Los comandos de chequeo pueden indicar un chequeo genérico silenciado desde T03, sustituido por la comprobación específica del índice de correo.

## Abrir la aplicación compilada

Con la preparación terminada:

```powershell
.\scripts\django.ps1 runserver 127.0.0.1:8000 --noreload --nostatic
```

Abrir `http://127.0.0.1:8000/`. Django entrega el documento y la API; WhiteNoise entrega los estáticos. `--nostatic` evita que el servidor de desarrollo sustituya esa entrega. El terminal queda ocupado por el servidor; Ctrl+C lo detiene.

La portada y `/acerca-de` son navegables. Recargar `/acerca-de` debe conservar la presentación. Una dirección como `/api/v1/no-existe/` devuelve **404 JSON**; eso confirma el límite de transporte, no una operación de negocio disponible. Registro, sesión por API y las demás funcionalidades se incorporan en sus sprints. `/admin/` permanece reservado sin habilitar administración Django.

Después de preparar el build, `npm run preview` desde `frontend` es un acceso abreviado a este mismo Django mediante PowerShell 7. No iniciar ambos comandos simultáneamente en 8000. La URL correcta es HTTP; abrir `frontend/index.html` como archivo no inicia Vue.

## Desarrollar con recarga de Vue

En un primer terminal, desde la raíz:

```powershell
.\.venv\Scripts\python.exe scripts\postgresql_local.py iniciar
.\scripts\django.ps1 runserver 127.0.0.1:8000 --noreload --nostatic
```

En otro terminal, dentro de `frontend`:

```powershell
npm run dev
```

Abrir `http://127.0.0.1:5173/`. Vite entrega la interfaz y reenvía `/api/`, `/admin/` y `/static/` a Django, conservando el origen. La recarga de Vue refleja las ediciones del cliente. Los cambios de servidor requieren reiniciarlo porque se utiliza `--noreload`. El banco sintético de componentes está únicamente en `http://127.0.0.1:5173/tests/fixtures/components.html`.

Para volver a comprobar la compilación, detener los procesos web, ejecutar `scripts/preparar-web.ps1` y reiniciar Django. Esto actualiza el documento, los recursos y el índice de WhiteNoise. Las políticas de caché están en [Entrega web](entrega-web.md).

Si se elige otro puerto HTTP, por ejemplo 8001 para Django y 5174 para Vite, arrancar Django con esa dirección y configurar el terminal del cliente:

```powershell
$env:ENTREPARES_API_TARGET = 'http://127.0.0.1:8001'
npm run dev -- --port 5174
```

El destino del proxy debe seguir siendo un origen local sin credenciales. No es una variable publicada en la aplicación compilada.

## Parar y volver a arrancar

Detener Django y Vite con Ctrl+C en sus terminales. Para detener también el PostgreSQL privado de esta copia:

```powershell
.\.venv\Scripts\python.exe scripts\postgresql_local.py detener
```

La parada conserva los datos. En la siguiente sesión, volver a la raíz del proyecto, usar `postgresql_local.py iniciar` y arrancar los procesos web; no hace falta reinstalar paquetes ni preparar otro cluster. `postgresql_local.py estado` muestra versión, puerto y estado del servidor propio. Volver a abrir el terminal o reiniciar Windows no exige regenerar credenciales. Aplicar nuevas migraciones con `scripts/django.ps1 migrate --noinput` cuando se incorporen al código.

## Comprobar el entorno

Con los procesos web detenidos:

```powershell
.\scripts\comprobar.ps1
.\scripts\comprobar.ps1 -ConPostgreSQL
```

La primera modalidad no necesita `.env` ni base y ya incluye tipos, pruebas y compilación. La segunda añade la integración y la revisión de migraciones: se elige una modalidad según el trabajo, no es necesario ejecutar ambas consecutivamente. Los registros están en `.cache/comprobaciones`. Consultar [Comprobaciones reproducibles](comprobaciones.md) para interpretar el informe y sus límites.

## Resolver fallos

| Síntoma | Comprobación y solución |
| --- | --- |
| `node`, `npm.cmd` o `pwsh` no se reconoce, o la versión no coincide | Comprobar PATH y versiones en ese terminal. Preparar las versiones requeridas y repetir `preparar-entorno.ps1`; el script no reemplaza instalaciones globales. |
| Descarga interrumpida o fallo de integridad | Repetir el paso de preparación. PostgreSQL puede reutilizar partes descargadas; el instalador vuelve a verificar el artefacto. Conservar la comprobación de SHA256 y revisar acceso al distribuidor si persiste. |
| `ENOSPC` al instalar paquetes | Revisar espacio en la unidad del proyecto y la ubicación del fallo en el registro. npm usa `.tools/npm-cache`; la copia limpia de T10 verificó esa solución. |
| Falta `.env` | Ejecutar `preparar-configuracion.ps1` desde esta copia y después preparar su PostgreSQL. La plantilla de ejemplo mantiene los secretos vacíos. |
| Puerto PostgreSQL ocupado en una copia nueva | Elegir otro con `preparar --port 55433` antes de crear el cluster. No detener el proceso ajeno para continuar. |
| Se rechaza cambiar el puerto de un cluster existente | Consultar `estado` y usar su puerto. El comando no migra automáticamente un cluster a otro puerto. |
| `.env` contiene un destino o credenciales ajenos | Revisar si se está trabajando en la carpeta correcta. El aprovisionamiento conserva esa configuración y se detiene; usar una copia nueva para otro entorno. |
| `connection refused`, autenticación fallida o tablas ausentes | Comprobar `estado`, arrancar el cluster propio y aplicar `migrate` después de prepararlo. Consultar los registros PostgreSQL de esa copia. |
| Directorio estático ausente, interfaz 503 o recursos que no cargan | Con el servidor detenido, ejecutar `preparar-web.ps1` y reiniciar Django con `--nostatic`. |
| 8000 o 5173 ocupado | Revisar si quedó abierto otro terminal del proyecto. Utilizar una pareja libre de puertos y configurar `ENTREPARES_API_TARGET` en el terminal de Vite si Django no usa 8000. No cerrar servicios no identificados. |
| Se edita `.env` pero Django usa otra configuración | Las variables del proceso prevalecen sobre `.env`. Revisar las variables de este proyecto o abrir un terminal limpio; no mostrar claves o contraseñas en diagnósticos compartidos. |
| La API devuelve `NOT_FOUND` o `/admin/` devuelve 404 | Revisar si la operación ya se implementó. No convertir esas direcciones en páginas Vue para ocultar el error. |
| Las pruebas rechazan la identificación de la base | Usar `comprobar.ps1 -ConPostgreSQL` o `probar.ps1` en la copia que preparó ese cluster. Conservar las comprobaciones de destino. |

Los registros privados de PostgreSQL están en `.tools/postgresql/17.11/servidor.log` y `operaciones.log`; los del flujo común, en `.cache/comprobaciones`. Al compartir un fallo, enviar el comando y su mensaje público, omitiendo `.env`, `secrets.json`, datos y cabeceras de autenticación. Las instrucciones de base, cliente y entrega se amplían en [PostgreSQL local](postgresql-local.md), [Cliente Vue](cliente-vue.md) y [Entrega web](entrega-web.md).

## Reproducción verificada

Se exportó la versión de runtime `2e562ed804d15b4156a5e5b7f90e23622844d358` a otra carpeta, con espacios en su nombre y sin `.env`, herramientas o dependencias instaladas. Se ejecutó esta secuencia con secretos generados allí y PostgreSQL propio en 55433. Se reutilizó únicamente el ZIP de distribución de PostgreSQL, comprobando su tamaño y SHA256; no se copiaron binarios extraídos, datos ni credenciales de otra instalación.

El entorno fue Windows 11 x64, PowerShell 7.6.5, Python 3.13.17, Node 24.18.0, npm 11.16.0, uv 0.13.6 y PostgreSQL 17.11. La nueva copia aplicó 16 migraciones y terminó con nueve tablas y cero cuentas de desarrollo. Pasaron 195 pruebas del servidor —176 sin base y 19 con PostgreSQL— y 68 del cliente, además de los demás controles del flujo común.

Se comprobaron en HTTP y navegador la interfaz compilada, la recarga de rutas y el modo Vite con proxy. Los 13 recursos versionados se compararon con la compilación. La API inexistente respondió 404 JSON en ambos modos, incluso solicitando HTML. Después se detuvieron y arrancaron PostgreSQL y Django: se conservaron configuración, identidad del cluster, esquema y datos; `migrate` no encontró cambios y el documento mantuvo su ETag. También se verificaron la conservación de `.env` al repetir su generador y los rechazos ante falta de configuración o intento de cambiar el puerto de un cluster existente.

Los procesos de revisión y el cluster de esa copia se detuvieron al terminar. El PostgreSQL del proyecto principal continuó activo y no se intervino el servicio global. La evidencia compacta y sus límites están en [arranque-reproducible.json](evidencias/arranque-reproducible.json); los registros y capturas permanecen privados en `.cache/arranque`.

Estos pasos corresponden a desarrollo local; el despliegue y TLS del piloto tienen sus tareas posteriores. El uso previsto de los comandos se contrastó con [Django](https://docs.djangoproject.com/en/5.2/ref/django-admin/), [pg_ctl de PostgreSQL 17](https://www.postgresql.org/docs/17/app-pg-ctl.html) y la [precedencia de variables de uv](https://docs.astral.sh/uv/concepts/configuration-files/#environment-variable-files).
