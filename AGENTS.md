# Instrucciones para trabajar en Entrepares

## Base de diseño

Leer `docs/arquitectura.md`, `docs/base-documental.json` y `docs/seguimiento.md` antes de modificar la estructura. La documentación de tesis indicada en el registro es la fuente de requisitos, permisos, datos y contratos. Si la copia local de una fuente no está disponible, conservar el alcance documentado y localizarla antes de cambiar sus decisiones.

La decisión técnica `docs/decisiones/DA03-E01-dependencias.md` actualiza DRF 3.16 a 3.18.3 por correcciones de seguridad. Consultar esa concreción antes de interpretar la referencia histórica. Conservar el formato de errores de OpenAPI al implementar la adaptación HTTP.

## Arquitectura

- Mantener un monolito modular con Vue y TypeScript, Django y DRF, y PostgreSQL. Los diez módulos de negocio están en `backend/modules` con los nombres establecidos.
- Cada módulo escribe sus propios datos. `backend/application` coordina los casos que involucran varios módulos, los permisos vigentes, las transacciones y los efectos persistentes.
- Los paquetes de negocio `models`, `commands`, `selectors` y `contracts` no importan HTTP ni `application`. Los puntos de entrada autorizados de Django en `management/commands` sí pueden llamar a `application`.
- `core` contiene solo utilidades técnicas mínimas. Las lecturas compartidas se delimitan en selectores documentados; las escrituras se solicitan al propietario.
- Crear el modelo de usuario propio antes de la primera migración de autenticación. No usar SQLite para acreditar integridad o concurrencia de PostgreSQL.
- Conservar un origen web para Vue y `/api/v1/`, sesiones de servidor y CSRF, incluso para las mutaciones anónimas que lo requieran. Los permisos se comprueban en el servidor por actor, contexto, acción y recurso.
- Mantener separados los contactos públicos de contenidos y los contactos de perfiles. Verificación personal, representación de una organización, afiliación declarada y distinción de investigador son condiciones distintas.
- Las políticas pendientes se aplican a la operación o parámetro afectados. No aprobar por inferencia propuestas que el registro mantiene pendientes ni bloquear por ellas todo un módulo.

## Datos y comprobaciones

- No incorporar secretos, respuestas de encuestas, entrevistas ni datos reales de participantes al repositorio. Usar datos sintéticos identificados para las comprobaciones de desarrollo.
- Fijar dependencias y documentar las instrucciones reproducibles al completar SP01-T02 y los siguientes trabajos de entorno.
- Ejecutar comprobaciones apropiadas al cambio. Distinguir una revisión de archivos de las pruebas sobre una aplicación ejecutable o de los resultados del piloto.
- Registrar los cambios de alcance y su motivo; conservar los identificadores de requisitos, módulos, operaciones y pruebas correspondientes.

## Interfaz pública

Usar los recursos de identidad visual de Entrepares y adaptar los componentes a móvil y computadora. Incluir en el pie un enlace pequeño, visible y funcional a `https://jorge-coffee.onrender.com/` con el texto «Apoyar a Jorge».
