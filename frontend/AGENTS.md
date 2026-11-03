# Cliente Vue de Entrepares

- Leer `docs/cliente-vue.md` de la raíz y conservar el monolito, el origen común y el cliente `src/api/client.ts`.
- Usar rutas relativas de API y cookies de sesión; no incorporar credenciales Django/PostgreSQL al cliente, tokens de sesión en almacenamiento web ni destinos externos de API en componentes.
- Los resultados correctos del transporte son `unknown`: cada funcionalidad debe validar su proyección conforme a OpenAPI. Los campos inesperados, permisos y contexto organizacional siguen comprobándose en el servidor.
- Mantener el token CSRF en memoria; el adaptador de login aplica `setCsrfToken` con el token renovado y el de logout descarta la caché. No reintentar automáticamente mutaciones ni quitar contexto organizacional al recibir una denegación.
- Conservar el estado real de cada incremento. Los datos de una maqueta no son datos del producto ni deben introducirse como resultados del piloto.
- Reutilizar recursos y licencias locales de la propuesta de identidad v1, foco visible, navegación por teclado y adaptación móvil. La biblioteca completa de componentes corresponde a SP01-T08.
- Mantener el enlace discreto «Apoyar a Jorge» en el pie público: https://jorge-coffee.onrender.com/.
