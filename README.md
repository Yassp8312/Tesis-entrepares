# Entrepares

Plataforma web para descubrir personas, proyectos y oportunidades de colaboración entre estudiantes, graduados y organizaciones del contexto cubano.

El producto contempla una bolsa de perfiles con acceso autorizado, oportunidades públicas de colaboración y publicaciones públicas de novedades y eventos. Las personas contactan por los medios externos que los responsables indiquen.

## Estado

Repositorio local de SP01 con estructura modular, dependencias fijadas, configuración Django, usuario propio y PostgreSQL de desarrollo y pruebas. Se han preparado SP01-T01 a SP01-T04. La migración inicial de `identity.Account` está aplicada sobre una base del proyecto y cuenta con pruebas de integración. Las funciones y pantallas del producto se incorporan en los incrementos posteriores.

La investigación sigue DSRM y el desarrollo utiliza OpenUP adaptado. La base de diseño establece Vue 3 y TypeScript para la interfaz, Django y Django REST Framework para el servidor y PostgreSQL para los datos, organizados como un monolito modular.

## Preparar el entorno

Con Node 24.18.0 y npm 11.16.0 disponibles, desde PowerShell en la raíz del repositorio:

```powershell
.\scripts\preparar-entorno.ps1
```

El script prepara uv y Python dentro de `.tools`, sincroniza `.venv` y `frontend/node_modules` desde sus archivos de bloqueo y ejecuta las comprobaciones técnicas de dependencias. No requiere activar el entorno virtual. Consulta [Entorno de desarrollo](docs/entorno.md) para versiones, comandos de verificación y alcance de los ensayos.

La referencia inicial DRF 3.16 se actualiza a 3.18.3 por correcciones de seguridad, según [DA03 E01](docs/decisiones/DA03-E01-dependencias.md).

## Configurar Django

```powershell
.\scripts\preparar-configuracion.ps1
.\scripts\django.ps1 check
.\.venv\Scripts\python.exe -m pytest -q
```

La configuración local se guarda en `.env`, excluido de Git, con una clave aleatoria que el script no sobrescribe. Los ajustes se separan en desarrollo, pruebas y producción. La invocación directa de pytest selecciona las pruebas sin base. Consulta [Configuración y cuenta](docs/configuracion-y-cuenta.md) para el modelo y los ajustes.

## Preparar PostgreSQL y comprobar la integración

```powershell
.\.venv\Scripts\python.exe scripts\postgresql_local.py preparar
.\scripts\django.ps1 migrate --noinput
.\scripts\probar.ps1 -Modo todas -q
```

Se prepara PostgreSQL 17.11 dentro de `.tools`, en un puerto local propio, con bases y credenciales separadas para desarrollo y pruebas. No utiliza el servicio PostgreSQL que pudiera existir en el equipo. Consulta [PostgreSQL local](docs/postgresql-local.md) para los privilegios, la protección de las pruebas y los comandos de arranque y parada.

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

La distribución de responsabilidades está en [Arquitectura](docs/arquitectura.md). Las referencias a los documentos de tesis y sus huellas están en [Base documental](docs/base-documental.json). El trabajo realizado se registra en [Seguimiento](docs/seguimiento.md).

## Reglas iniciales

- Mantener la propiedad de datos de cada módulo y coordinar las operaciones entre módulos desde `application`.
- Crear el usuario propio de Django antes de aplicar la primera migración de autenticación.
- Conservar los contratos `/api/v1/`, las sesiones de servidor y la protección CSRF definidos en el diseño.
- Mantener secretos, bases locales, copias y datos de participantes fuera de Git. Los ejemplos de configuración usarán valores ficticios.
- Consultar las condiciones de cada operación antes de implementar una función pendiente de una decisión de producto.

La interfaz pública incorporará en su pie un enlace discreto a [Apoyar a Jorge](https://jorge-coffee.onrender.com/).
