# DA03 E01 Dependencias de implementación

Fecha: 30 de octubre de 2026. Decisión técnica de implementación asociada a DA03 y SP01-T02.

## Decisión

Usar Python 3.13.17, Django 5.2.18 y Django REST Framework 3.18.3. Se conserva el monolito modular, PostgreSQL 17, Vue 3, el origen único, las sesiones de servidor y CSRF. Los archivos `uv.lock` y `frontend/package-lock.json` fijan los paquetes transitivos y los artefactos correspondientes. uv 0.13.6 gestiona el entorno Python y npm 11.16.0 el cliente con Node 24.18.0.

El registro original propone DRF 3.16 como serie de referencia y exige documentar cambios de serie. La auditoría inicial de 3.16.1 produjo siete registros que corresponden a cinco avisos distintos, al agrupar alias GHSA y PYSEC. Las correcciones relevantes se publicaron en DRF 3.17.2 y 3.18.2. Se selecciona 3.18.3, que incluye esas correcciones y una reparación posterior de compatibilidad. La ficha publicada exige Django 5.2 o superior y Python 3.10 o superior, compatibles con la base elegida.

## Impacto y comprobación

El salto de serie requiere controlar los errores de serializadores de listas, cuyo formato nativo cambia en 3.18. La capa HTTP de SP01-T06 debe normalizar los errores conforme al contrato OpenAPI; el formato interno de DRF no define por sí mismo la respuesta pública. La retirada de coreapi y del soporte a versiones antiguas de Python o Django no afecta a esta base. Las pruebas CT de los endpoints se ejecutarán cuando exista la API.

Vue Router se fija en 4.6.4 y TypeScript en 5.9.3 como conjunto ensayado con Vue 3.5.44, Vite 8.3.5 y vue-tsc 3.3.14. Estas versiones concretan herramientas de la serie Vue 3 y no amplían funciones del producto. Gunicorn se declara para sistemas distintos de Windows y se comprobará ejecutándolo en Linux durante la preparación del despliegue; su instalación no se atribuye al entorno Windows.

PostgreSQL local es 17.5. La preparación de una base del proyecto y la revisión de su parche vigente corresponden a SP01-T04. Esta decisión no actualiza el servicio existente ni acredita una conexión o migración.

## Fuentes verificadas

- [Notas oficiales de DRF](https://www.django-rest-framework.org/community/release-notes/), apartados 3.17 y 3.18.
- [Aviso del proyecto sobre negociación de contenido](https://github.com/encode/django-rest-framework/security/advisories/GHSA-33wh-fxxf-88vv).
- [Aviso del proyecto sobre AdminRenderer](https://github.com/encode/django-rest-framework/security/advisories/GHSA-g47c-3xmw-q6m2).
- [Metadatos de DRF 3.18.3 en PyPI](https://pypi.org/pypi/djangorestframework/3.18.3/json).
- [Requisitos de PostgreSQL en Django 5.2](https://docs.djangoproject.com/en/5.2/ref/databases/#postgresql-notes).
