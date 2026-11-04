# Entorno de desarrollo

Preparación de SP01-T02, 30 de octubre de 2026. El conjunto se comprueba en Windows x64. El servidor y los modelos de negocio se incorporarán en los trabajos siguientes de SP01.

## Versiones fijadas

| Componente | Versión | Función |
| --- | --- | --- |
| Python | 3.13.17 | Intérprete del servidor |
| uv | 0.13.6 | Resolución, bloqueo y entorno virtual |
| Django | 5.2.18 | Framework web |
| Django REST Framework | 3.18.3 | Adaptación HTTP de la API |
| psycopg y psycopg-binary | 3.3.6 | Adaptador PostgreSQL |
| WhiteNoise | 6.12.0 | Archivos estáticos públicos |
| Gunicorn | 26.2.0 | WSGI, declarado para sistemas distintos de Windows |
| pytest y pytest-django | 9.2.0 y 4.14.0 | Herramientas de pruebas |
| Ruff | 0.17.3 | Análisis y formato Python |
| Node y npm | 24.18.0 y 11.16.0 | Entorno y gestor del cliente |
| Vue y Vue Router | 3.5.44 y 4.6.4 | Componentes y navegación |
| TypeScript | 5.9.3 | Comprobación de tipos |
| Vite y plugin-vue | 8.3.5 y 6.0.10 | Construcción del cliente |
| vue-tsc | 3.3.14 | Tipos en componentes Vue |
| Tipos de Node | 24.19.2 | Declaraciones de desarrollo |

`pyproject.toml` declara las dependencias Python y `uv.lock` fija las transitivas y sus artefactos. El proyecto es virtual para uv: no se instala como una distribución Python. `.python-version` selecciona el parche del intérprete. `frontend/package.json` y `frontend/package-lock.json` hacen lo mismo para el cliente; `.node-version` y los requisitos de `engines` fijan Node y npm. Se utiliza el índice público de PyPI y el registro público de npm.

La modificación de la referencia DRF 3.16 se justifica en [DA03 E01](decisiones/DA03-E01-dependencias.md). Las versiones fijadas son la base comprobada de este incremento, no una garantía de vigencia futura. Una actualización requiere regenerar bloqueos y repetir las comprobaciones afectadas.

## Preparación en Windows

La máquina utilizada dispone de Node y npm en las versiones indicadas. En otra máquina se deben preparar esas versiones desde [Node.js](https://nodejs.org/). El script comprueba las versiones y no las sustituye globalmente.

Desde PowerShell, en la raíz:

```powershell
.\scripts\preparar-entorno.ps1
```

El script descarga la distribución Windows x64 de uv 0.13.6 desde PyPI y verifica la huella SHA256 fijada antes de extraer el ejecutable. Conserva uv, el intérprete y su caché en `.tools`; instala Python sin registrar asociaciones ni añadir ejecutables al PATH. El entorno virtual se crea en `.venv`. Estos directorios y `node_modules` están excluidos de Git.

No se requiere una instalación global adicional de Python ni activar `.venv`. El script instala a partir de los bloqueos con `uv sync --locked` y `npm ci`. Si una descarga falla su comprobación de integridad, no se utiliza.

Desde SP01-T10, `npm ci` utiliza la caché propia `.tools/npm-cache`. El flujo común posterior es `scripts/comprobar.ps1`, descrito en [Comprobaciones reproducibles](comprobaciones.md); no necesita `.env` para su modalidad sin base.

La secuencia actual completa, incluido PostgreSQL, migraciones, build y apertura de la aplicación, está en [Instalación y arranque](instalacion-y-arranque.md). Su reproducción con otro cluster se comprobó en SP01-T11; los resultados de preparación de T02 que siguen conservan su alcance histórico.

## Repetir las comprobaciones

Con el entorno preparado, desde la raíz:

```powershell
.\.venv\Scripts\python.exe scripts\verificar_dependencias.py
.\.venv\Scripts\ruff.exe check backend scripts
```

Desde `frontend`:

```powershell
npm run check:deps
```

La primera comprobación carga Django, DRF y el adaptador PostgreSQL con ajustes sintéticos. La segunda analiza el código Python. La tercera comprueba un componente Vue con TypeScript, lo compila mediante Vite y recorre una ruta en memoria. La muestra técnica de frontend se genera en `.cache`; no forma parte de la interfaz de Entrepares.

La repetición de la instalación en una carpeta independiente utiliza un entorno virtual y un `node_modules` nuevos. Se comparan todas las versiones Python y las huellas de ambos archivos de bloqueo. Se reutilizan las cachés de descargas; no se presenta como una instalación sin acceso a Internet ni como validación de otro sistema operativo.

## Otros sistemas y preparación de la base

En Linux, con uv 0.13.6, Python 3.13.17, Node y npm en las versiones fijadas, los comandos equivalentes son:

```sh
uv sync --locked
uv run --locked python scripts/verificar_dependencias.py
cd frontend
npm ci
npm run check:deps
```

Son instrucciones de reproducción; este incremento no acredita una ejecución Linux de Gunicorn o de la aplicación. La instalación de uv está documentada por [Astral](https://docs.astral.sh/uv/getting-started/installation/).

PostgreSQL mantiene la serie 17 del diseño. Se detectaron binarios 17.5 en el equipo, sin intervenir su servicio. SP01-T04 preparará la base del proyecto y revisará el parche vigente de la serie antes de configurarla. Esta entrega comprueba la carga del adaptador binario; no abre una conexión ni crea tablas. El modelo de usuario propio debe existir antes de aplicar la primera migración de autenticación.

## Dependencias y seguridad

Las auditorías de este corte se registran en `evidencias/dependencias.json`. Se consultan nuevamente al cambiar bloqueos o antes del despliegue; no sustituyen las pruebas de autorización y seguridad del producto. Con uv disponible se puede ejecutar `uv audit --locked`; en `frontend`, `npm audit`. La salida JSON de `uv audit` es experimental en la versión utilizada.

Las compatibilidades de referencia se contrastaron con la [documentación de Django](https://docs.djangoproject.com/en/5.2/ref/databases/#postgresql-notes), las [notas de DRF](https://www.django-rest-framework.org/community/release-notes/), la [guía de Vite](https://vite.dev/guide/) y la [instalación de psycopg](https://www.psycopg.org/psycopg3/docs/basic/install.html).
