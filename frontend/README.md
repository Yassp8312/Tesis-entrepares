# Interfaz de Entrepares

Esta carpeta reserva el cliente Vue 3 con TypeScript. `src/api` contendrá el cliente HTTP común y `src/features` las funcionalidades de la interfaz. Las dependencias y sus versiones están en `package.json` y `package-lock.json`; la aplicación Vue se incorporará en SP01-T07.

Con Node y npm en las versiones fijadas, ejecutar `npm ci` para instalar y `npm run check:deps` para comprobar tipos, compilación y navegación en memoria. Este último comando usa una muestra técnica dentro de `.cache`, excluida de Git; no crea pantallas del producto.

La maqueta y los recursos de marca se conservan en la carpeta de identidad visual de la tesis. Al integrarlos, los ejemplos ficticios deben mantenerse diferenciados de los datos del producto. La futura interfaz utilizará el mismo origen que la API y conservará el enlace discreto «Apoyar a Jorge» en su pie público.
