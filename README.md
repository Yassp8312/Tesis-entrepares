# Entrepares

Plataforma web para descubrir personas, proyectos y oportunidades de colaboración entre estudiantes, graduados y organizaciones del contexto cubano.

El producto contempla una bolsa de perfiles con acceso autorizado, oportunidades públicas de colaboración y publicaciones públicas de novedades y eventos. Las personas contactan por los medios externos que los responsables indiquen.

## Estado

SP01 completado en su alcance de entorno y esqueleto: estructura modular, dependencias fijadas, configuración Django, usuario propio, PostgreSQL, cliente Vue, componentes comunes y entrega compilada. La instalación, pruebas y arranque se reprodujeron en otra copia con credenciales y cluster propios. Las operaciones de negocio y sus pantallas se incorporan en los incrementos posteriores; el cierre de este sprint no acredita el piloto ni termina los trabajos transversales de infraestructura.

SP02 está en curso, con T01–T08 completadas. Incorpora [comprobaciones y recuperación](docs/comprobaciones-y-recuperacion.md), [catálogos y ámbitos académicos](docs/catalogos-y-ambitos.md), [organizaciones y representación](docs/organizaciones-y-representacion.md), [perfiles y formación](docs/perfiles-y-formacion.md), [respaldos y distinciones](docs/respaldos-y-distinciones.md), [capacidades y delegaciones](docs/capacidades-y-delegaciones.md), [auditoría mínima](docs/auditoria-minima.md) y [oportunidades y financiación](docs/oportunidades-y-financiacion.md), con restricciones e integridad referencial comprobadas en PostgreSQL. M10 incorpora una interfaz de escritura con proyecciones cerradas. El siguiente trabajo es migrar divulgación y destacados (SP02-T09).

La investigación sigue DSRM y el desarrollo utiliza OpenUP adaptado. La base de diseño establece Vue 3 y TypeScript para la interfaz, Django y Django REST Framework para el servidor y PostgreSQL para los datos, organizados como un monolito modular.

## Instalar el entorno local

Con Node 24.18.0 y npm 11.16.0 disponibles, desde PowerShell en la raíz del repositorio:

```powershell
.\scripts\preparar-entorno.ps1
.\scripts\preparar-configuracion.ps1
.\.venv\Scripts\python.exe scripts\postgresql_local.py preparar
.\scripts\preparar-web.ps1
.\scripts\django.ps1 migrate --noinput
.\scripts\django.ps1 check --database default --fail-level WARNING
```

La secuencia prepara herramientas y dependencias locales, genera `.env`, prepara PostgreSQL 17.11 en un puerto privado, compila Vue y aplica las migraciones disponibles. No requiere activar `.venv` ni Docker. Si 55432 está ocupado en una copia nueva, usar `preparar --port 55433` en el tercer paso. La [guía de instalación y arranque](docs/instalacion-y-arranque.md) explica el orden, puertos, reinicio y solución de fallos; [Entorno de desarrollo](docs/entorno.md) identifica las versiones.

La referencia inicial DRF 3.16 se actualiza a 3.18.3 por correcciones de seguridad, según [DA03 E01](docs/decisiones/DA03-E01-dependencias.md).

## Comprobaciones del proyecto

Con el entorno preparado, `scripts/comprobar.ps1` ejecuta arquitectura, dependencias, formato Python, pruebas, tipos Vue/TypeScript, compilación y colección de estáticos sin necesitar `.env` ni una base. `scripts/comprobar.ps1 -ConPostgreSQL` añade la integración en el cluster privado ya configurado y la comprobación de migraciones. Ejecutar con el proceso web detenido; el informe y los registros quedan en `.cache/comprobaciones`. Consulta [Comprobaciones reproducibles](docs/comprobaciones.md) para los comandos, reglas y resultados de la copia independiente.

## Abrir la aplicación

```powershell
.\.venv\Scripts\python.exe scripts\postgresql_local.py iniciar
.\scripts\django.ps1 runserver 127.0.0.1:8000 --noreload --nostatic
```

Abrir `http://127.0.0.1:8000/`. Ctrl+C detiene Django. Después puede detenerse el cluster propio con `postgresql_local.py detener`; sus datos se conservan. La configuración local permanece excluida de Git y no se sobrescribe al repetir su generador. Consulta [Configuración y cuenta](docs/configuracion-y-cuenta.md) para el modelo y los ajustes.

PostgreSQL utiliza sus propios binarios, bases y credenciales de desarrollo y pruebas. Consulta [PostgreSQL local](docs/postgresql-local.md) para privilegios, protección de las pruebas y control del servidor. [Comprobaciones reproducibles](docs/comprobaciones.md) explica los comandos de validación.

## Estructura

```text
frontend/
  src/
    api/                 Cliente HTTP y tipos de respuestas
    features/            Funcionalidades de la interfaz
backend/
  config/                Configuración, rutas y WSGI
  api/v1/                Entrada HTTP y proyecciones autorizadas
  application/           Casos de uso y coordinación transaccional
  modules/               Diez módulos propietarios de sus datos
  core/                  Tipos y utilidades técnicas mínimas
docs/                    Arquitectura, referencias y seguimiento
```

La distribución de responsabilidades está en [Arquitectura](docs/arquitectura.md) y los límites de lectura, escritura y tiempo en [Contratos internos y reloj](docs/contratos-y-reloj.md). Las referencias a los documentos de tesis y sus huellas están en [Base documental](docs/base-documental.json). El trabajo realizado se registra en [Seguimiento](docs/seguimiento.md).

La base HTTP se describe en [Entrada JSON y errores](docs/entrada-json.md). Por ahora las rutas desconocidas de `/api/v1/` responden 404 JSON; las operaciones de negocio se registrarán en sus tareas. Las rutas sintéticas de las pruebas no se publican en el producto.

Para editar la interfaz, iniciar Django con `scripts/django.ps1 runserver 127.0.0.1:8000 --noreload --nostatic` y, en otra terminal dentro de `frontend`, ejecutar `npm run dev`. Abrir `http://127.0.0.1:5173/`. Los comandos, ciclo CSRF, recursos y pruebas están en [Cliente Vue](docs/cliente-vue.md).

La biblioteca de botones, campos, estados, avisos y diálogo se describe en [Componentes visuales](docs/componentes-visuales.md), con un banco local de pruebas separado de la navegación pública. La aplicación requiere HTTP; abrir `frontend/index.html` directamente como archivo no inicia Vue.

Para abrir la interfaz compilada desde Django, con el proceso web detenido, ejecutar `scripts/preparar-web.ps1` y después `scripts/django.ps1 runserver 127.0.0.1:8000 --noreload --nostatic`. Abrir `http://127.0.0.1:8000/`. La separación del HTML, `collectstatic`, caché y recarga de rutas se explican en [Entrega web](docs/entrega-web.md).

## Reglas iniciales

- Mantener la propiedad de datos de cada módulo y coordinar las operaciones entre módulos desde `application`.
- Crear el usuario propio de Django antes de aplicar la primera migración de autenticación.
- Conservar los contratos `/api/v1/`, las sesiones de servidor y la protección CSRF definidos en el diseño.
- Mantener secretos, bases locales, copias y datos de participantes fuera de Git. Los ejemplos de configuración usarán valores ficticios.
- Consultar las condiciones de cada operación antes de implementar una función pendiente de una decisión de producto.

La interfaz pública incluye en su pie un enlace discreto a [Apoyar a Jorge](https://jorge-coffee.onrender.com/).
