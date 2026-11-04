# Comprobaciones reproducibles

SP01-T10, cierre el 4 de noviembre de 2026. Un comando reúne las comprobaciones técnicas de Entrepares y conserva sus resultados. Reutiliza las pruebas de T03–T09 y el control de límites de T05, con un ejecutor independiente para examinar archivos reales.

## Uso habitual

Con el entorno instalado mediante `scripts/preparar-entorno.ps1`, desde la raíz:

```powershell
.\scripts\comprobar.ps1
```

Este modo no lee `.env`, no prepara PostgreSQL ni ejecuta pruebas que requieran una base. Utiliza ajustes sintéticos para las pruebas y `config.settings.checks` para comprobar Django y recolectar los recursos preparados. Compila Vue y escribe únicamente artefactos locales de comprobación; ejecutar con el proceso web detenido, como indica [Entrega web](entrega-web.md).

Para añadir las pruebas contra el cluster privado ya preparado y comprobar migraciones:

```powershell
.\scripts\comprobar.ps1 -ConPostgreSQL
```

Esta opción llama a `scripts/probar.ps1 integracion`, que reconoce el cluster mediante su identificación y los destinos previstos antes de crear o eliminar la base efímera. Requiere `.env` y el PostgreSQL local del proyecto. No prepara otro cluster ni sustituye su configuración. Las pruebas sin base no se repiten al añadir la integración.

La implementación es `scripts/comprobar_proyecto.py`; el acceso PowerShell utiliza el Python de `.venv`. Las versiones de Node, npm y uv se verifican antes de continuar. El flujo se detiene al fallar una etapa y devuelve un código distinto de cero; no presenta un informe incompleto como correcto.

## Etapas e informes

| Etapa | Comprobación |
| --- | --- |
| Herramientas y arquitectura | Versiones fijadas y dependencias estáticas de los paquetes propietarios y `core`. |
| Dependencias Python | Vigencia de `uv.lock` con `uv lock --check --offline`, compatibilidad instalada y versiones directas y de desarrollo fijadas en `pyproject.toml`. |
| Análisis y formato | Ruff sobre `backend` y `scripts`, sin aplicar correcciones al ejecutar el flujo. |
| Servidor sin base | Pytest con selección explícita `not postgresql`, ajustes de prueba, JUnit y carpeta temporal propia. Incluye la comparación de modelos y migraciones sin conexión. |
| Cliente | Árbol instalado de npm, muestra de compatibilidad Vue, pruebas Node con JUnit y compilación con comprobación real de tipos Vue/TypeScript. |
| Entrega | Validación y separación del build, Django check y `collectstatic` con ajustes sintéticos. |
| PostgreSQL, opcional | Casos de integración y comprobación de migraciones mediante los scripts existentes. |

Cada ejecución crea `.cache/comprobaciones/<instante-UTC>-<identificador>/informe.json`, registros por etapa y archivos JUnit. El informe identifica comandos, códigos de salida, duración, huellas de los bloqueos, modalidad y recuentos de pruebas. Su campo `completed` solo es verdadero al terminar correctamente. No se sobrescriben informes anteriores ni se versionan esos registros.

El ejecutor filtra variables heredadas de Django, PostgreSQL, correo, pytest, Vite, configuración personalizada de Entrepares, uv y npm, además de `PYTHONPATH` y `NODE_OPTIONS`. Establece las rutas uv del propio checkout y UTF-8 para los procesos de comprobación. Solo la opción de integración utiliza explícitamente los scripts que cargan `.env`. La preparación de dependencias utiliza una caché npm local en `.tools/npm-cache`; se incorporó tras un fallo de espacio observado con la caché del sistema.

## Límites entre paquetes

Para comprobar únicamente la estructura, sin configurar Django:

```powershell
.\.venv\Scripts\python.exe scripts\verificar_arquitectura.py
```

El JSON enumera archivos examinados y violaciones con archivo relativo, línea, destino y regla. El proceso devuelve 0 si pasa, 1 ante una infracción y 2 si no puede examinar el destino. Examina los archivos Python de `backend/core` y `backend/modules`, excluyendo los paquetes de pruebas; no ejecuta los archivos examinados.

- `ARCH01`: `core` depende de biblioteca estándar y de sus utilidades internas.
- `ARCH02`: un propietario no importa HTTP, la API ni DRF.
- `ARCH03`: un propietario no importa `application`, salvo un archivo de comando situado directamente en `modules/<propietario>/management/commands/`. Los inicializadores de paquetes no reciben esa excepción.
- `ARCH04`: un propietario no importa modelos de otro módulo.
- `ARCH05`: una sintaxis o importación relativa inválida impide aprobar el archivo.

Se resuelven importaciones relativas y alias y se reconocen también referencias con prefijo `backend.`. Las entradas HTTP pueden llamar a `application`; no se aplica a ellas la regla de los paquetes propietarios. Las pruebas conservan la comprobación de las interfaces de los diez módulos. La excepción de CLI se concreta en [DA05 E02](decisiones/DA05-E02-control-de-estructura.md).

Este control analiza imports declarados. No demuestra todas las escrituras SQL, dependencias obtenidas dinámicamente, accesos a atributos de módulos o autorización de cada operación. Las reglas transaccionales y de acceso se evalúan en sus casos funcionales. No hay un análisis de tipos Python añadido; los tipos comprobados aquí son los del cliente Vue/TypeScript.

## Reproducción comprobada

Se exportó un árbol candidato de Git a una carpeta independiente. El inventario inicial no contenía `.env`, `.venv`, `node_modules` ni `.tools`. Se instalaron Python 3.13.17, los 16 paquetes Python del entorno Windows y 54 paquetes npm con los bloqueos, creando entornos propios. Se utilizaron los repositorios públicos y las cachés de descargas disponibles; no se acredita instalación sin Internet.

La copia ejecutó el flujo habitual completo: **176 pruebas de servidor sin base y 68 de cliente**, sin fallos ni omisiones, tipos, build y colección. Se introdujeron en el entorno del proceso valores sintéticos incompatibles para `NODE_OPTIONS`, `PYTEST_ADDOPTS` y configuración del proyecto; el flujo mantuvo su entorno aislado. La copia permaneció sin `.env` y no se le preparó un cluster.

En el proyecto principal se completó también el modo con PostgreSQL: **176 pruebas sin base, 19 de integración y 68 del cliente**, todas correctas. Las 25 pruebas de estructura incluyen siete casos nuevos respecto a T05: prefijo alternativo, inicializador CLI, entrada HTTP y ejecución del comprobador sobre archivos temporales. En total son **195 pruebas de servidor**. No se alteraron dependencias fijadas o bloqueos.

Además se inyectó una importación de `application` en un archivo de negocio de la copia: el comprobador y el flujo devolvieron 1 y se detuvieron en arquitectura antes de ejecutar pruebas. Después, un comando Django temporal autorizado llamó a un caso sintético de `application` y devolvió el resultado esperado sin conexión a la base. Se retiraron los archivos sintéticos, se repitió el control estático y se verificó que los 196 archivos de la exportación conservaran sus bytes.

Los resultados compactos están en [automatizacion.json](evidencias/automatizacion.json), con originales en `.cache/automatizacion` y `.cache/comprobaciones`. Es evidencia técnica parcial de AT01/AT18 y RNF14, relacionada con WI06/WI09. La reproducción se realizó en Windows x64 con PowerShell 7; no ejecuta publicación, infraestructura de CI remota, despliegue Linux ni evaluación del piloto. SP01-T11 completará las instrucciones de arranque y solución de fallos; SP01 sigue abierto.

Referencias: [uv: sincronización y bloqueo](https://docs.astral.sh/uv/concepts/projects/sync/), [Ruff: configuración](https://docs.astral.sh/ruff/configuration/), [pytest: informes](https://docs.pytest.org/en/stable/how-to/output.html#creating-junitxml-format-files), [npm ci](https://docs.npmjs.com/cli/v11/commands/npm-ci/).
