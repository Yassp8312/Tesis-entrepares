# Entrepares

Plataforma web para descubrir personas, proyectos y oportunidades de colaboración entre estudiantes, graduados y organizaciones del contexto cubano.

El producto contempla una bolsa de perfiles con acceso autorizado, oportunidades públicas de colaboración y publicaciones públicas de novedades y eventos. Las personas contactan por los medios externos que los responsables indiquen.

## Estado

Repositorio local inicial de SP01. Incluye la estructura de directorios y las reglas de trabajo; la aplicación todavía no tiene arranque, dependencias instaladas ni migraciones. El siguiente trabajo es resolver y fijar las versiones compatibles de las herramientas en SP01-T02.

La investigación sigue DSRM y el desarrollo utiliza OpenUP adaptado. La base de diseño establece Vue 3 y TypeScript para la interfaz, Django y Django REST Framework para el servidor y PostgreSQL para los datos, organizados como un monolito modular.

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
