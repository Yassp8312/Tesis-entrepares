# DA02 E02: documento y estáticos del mismo origen

3 de noviembre de 2026, SP01-T09. Concreta DA02 y RNF14 sin modificar las fuentes históricas de diseño.

La aplicación compilada se entrega mediante Django. Vite produce recursos bajo `/static/entrepares/`, manteniendo las rutas de Vue en la raíz. Durante el desarrollo, Vite conserva su base `/` y el proxy establecido en T07. El manifiesto de compilación permite comprobar que existen también los módulos cargados de forma diferida.

`preparar_web.py` valida el build antes de sustituir el HTML preparado, separa `index.html` de los recursos públicos y genera una lista privada de URL versionadas. El manifiesto `.vite`, el HTML y esa lista quedan fuera del directorio recolectado. Se conservan archivos de recursos de preparaciones anteriores para permitir que documentos abiertos terminen de cargar sus módulos; la limpieza de versiones pertenece al procedimiento de despliegue posterior.

Se utiliza `CompressedStaticFilesStorage` de WhiteNoise, ya instalado, en desarrollo y producción. Sustituye la configuración inicial `CompressedManifestStaticFilesStorage`: Vite es responsable de los nombres y referencias de sus módulos, CSS e imágenes. Reescribir o eliminar esos nombres mediante un segundo sistema de hashes complicaría los imports. La colección conserva sus bytes y añade las variantes comprimidas. Los archivos sin versión, incluidos favicon, licencias y recursos de terceros recolectados, se revalidan; no reciben caché inmutable por parecer un nombre con hash.

WhiteNoise identifica como inmutable exclusivamente una URL incluida en la lista generada desde el manifiesto validado de Vite. La política es `public, max-age=31536000, immutable`. Los demás estáticos tienen `no-cache, max-age=0, must-revalidate`. Las funciones de personalización se pasan como referencias Python invocables; una cadena en `WHITENOISE_IMMUTABLE_FILE_TEST` sería una expresión regular, no una ruta de importación. Se mantiene WhiteNoise después de SecurityMiddleware y dentro del límite API existente.

El documento inicial usa ETag SHA256 del contenido y `no-cache, max-age=0, must-revalidate`, con `Vary: Accept`. Se vuelve a leer para cada navegación; una versión nueva cambia el ETag. Los GET/HEAD condicionales pueden devolver 304. La respuesta no contiene información de sesión o de personas ni genera un token CSRF. La obtención funcional de CSRF sigue en SP03-T03.

El resolver reserva primero `/api/`; conserva sus errores JSON, incluso cuando se solicita HTML. Reserva también `/admin/` y `/static/`, incluidos los nombres sin barra. La administración no se habilita en este incremento. El retorno HTML solo procesa GET/HEAD de navegación compatible con HTML y no interpreta la ruta solicitada como un archivo. Las rutas de archivo o privadas examinadas devuelven 404, y la ausencia de build produce 503 controlado. Una ruta de navegación desconocida recibe el documento y Vue muestra su página no encontrada.

La preparación se realiza con el proceso web detenido: compilar, separar artefactos, ejecutar `collectstatic` y reiniciar Django/WSGI. El reinicio actualiza tanto el índice de WhiteNoise como la lista de recursos versionados almacenada en memoria. Este incremento no implementa publicación en caliente, reversión de releases ni un despliegue Linux/TLS.

Referencias: [Django staticfiles](https://docs.djangoproject.com/en/5.2/ref/contrib/staticfiles/), [WhiteNoise](https://whitenoise.readthedocs.io/en/stable/django.html), [integración Vite](https://vite.dev/guide/backend-integration.html), [respuestas condicionales](https://docs.djangoproject.com/en/5.2/topics/conditional-view-processing/). La evidencia de ejecución se conserva en [entrega-web.json](../evidencias/entrega-web.json).
