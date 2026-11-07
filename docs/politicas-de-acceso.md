# Políticas de acceso puras

SP02-T13 incorpora las decisiones de M08 en `backend/modules/access/policies.py`, con contratos inmutables en `contracts`. Corresponde a WI08, DL07/DL14/DL15 y RNF01/RNF03/RNF06; aporta evidencia parcial a AT01/AT04/AT06. Las siete fuentes identificadas en `base-documental.json` conservan sus versiones históricas.

## Contrato y responsabilidad

`authorize(action, actor, context, resource, facts, now)` recibe argumentos por nombre y devuelve `AccessDecision`: `allowed`, un código y, cuando corresponde, las condiciones pendientes. Una decisión denegada también es falsa al convertirla a booleano. Una acción desconocida, un recurso incompatible o hechos sin los tipos internos se deniegan. Una fecha sin zona o unos contratos mal construidos se rechazan como errores de programación; no se interpretan silenciosamente.

`now` es obligatorio y consciente de zona; se normaliza a UTC sin leer el reloj. La función no importa Django, HTTP ni modelos, no consulta bases, no modifica los hechos y no lee configuración ambiental. Los contratos emplean UUID, códigos, booleanos, fechas y colecciones inmutables; no necesitan contraseñas, tokens, correos o documentos de identidad.

Los hechos los construye `application` desde interfaces de los propietarios: cuenta activa de M01, completitud/contactos de M02, respaldo y ámbitos de M03, organización y representación de M04, contenido de M05/M06, medidas de M07 y concesiones de M08. Se aportan los ancestros académicos y de concesiones completos que requiera la decisión. No se deserializan estos DTO desde el cuerpo de una petición. Las raíces confiadas, condiciones configuradas y tipos de auditoría permitidos proceden exclusivamente del servidor y de procedimientos acreditados.

La decisión autoriza la acción indicada en ese instante y sobre esos hechos. **No es un ticket reutilizable ni una validación completa del caso funcional.** El coordinador debe reconstruir o revalidar los hechos vigentes, derivar el ámbito real del recurso y coordinar bloqueos y transacciones cuando haya cambios. Debe comprobar además estados/transiciones, contenido, versiones concurrentes, evidencias y procedimientos PB/Q aplicables. Un permiso para consultar un expediente no aprueba su resolución.

Esta tarea no conecta endpoints, cambia el permiso HTTP por defecto, crea capacidades o concesiones, habilita bloqueos reales ni añade selectores de autorización. La adaptación a cada operación y su prueba de integración corresponden a los incrementos funcionales.

## Actor, contexto y recurso

| Familia de acciones internas | Decisión implementada |
| --- | --- |
| Lectura pública de oportunidades | Contexto público, visible, publicada, estado active y vencimiento posterior al instante. No se publica un archivo cerrado/vencido por inferencia. |
| Lectura pública de novedades/eventos | Contexto público, visible y publicada, sin exigir sesión. |
| Perfil público organizacional | Proyección publicada/visible y entidad verificada. El propietario deberá acreditar la publicación de esa proyección; no se añade un estado a T15. |
| Bolsa | Contexto personal con verificación personal, o contexto de la entidad exacta con representación vigente de una organización verificada. No exige completitud del perfil del lector. |
| Perfil ajeno/contacto | Derecho a la bolsa y perfil completo. Solo se autorizan contactos marcados visibles. El respaldo del titular no es requisito para que aparezca su perfil completo. |
| Perfil propio | Cuenta activa y contexto personal del titular; puede completarlo y gestionar sus contactos antes de verificarse. |
| Contenido personal | Titularidad de la cuenta y verificación personal; representar una entidad no sustituye este respaldo. |
| Contenido organizacional | Titularidad de la entidad seleccionada y representación actual de ella, sin exigir respaldo personal. El autor material no se convierte en titular. |
| Gestión de la entidad | Representación actual y coincidencia con la entidad exacta. |
| Reporte | Contexto personal verificado y destino de tipo admitido. El caso debe comprobar que el destino concreto se puede reportar. PB05 no habilita reportes organizacionales. |
| Medida propia y solicitud de revisión | Cuenta activa, contexto personal y afectado exacto; sin exigir verificación, concesión administrativa o ausencia de bloqueo. |

`is_staff` e `is_superuser` se reciben como hechos técnicos, pero no conceden ninguna capacidad del producto. Un título de docente, la afiliación declarada, una distinción o un mérito tampoco los sustituyen. Los contratos no deducen el respaldo personal de la organización ni reinterpretan una verificación aprobada porque cambie una formación.

La representación debe comenzar antes o en `now`, no estar revocada y corresponder a la cuenta y entidad exactas. Se exige una única representación actual; hechos actuales contradictorios se deniegan. Un vínculo revocado puede coexistir con otro nuevo: conservar su historial no invalida la reincorporación. Revocar no elimina contenido ni quita derechos personales independientes.

Los nombres del enum `Action` son un catálogo interno cerrado, no endpoints habilitados ni semillas de T32. `opportunities.manage.read` y `publications.manage.read` son consultas privadas; no autorizan cambios. La actualización de una oportunidad tiene `opportunities.update`; la modificación/retirada de divulgación tiene `publications.mutate` y conserva RF45. El coordinador deberá enlazar cada operación con su acción exacta; no puede usar una consulta como permiso general de escritura.

## Capacidades y delegaciones

`check_capability(actor, capability_code, scope, facts, now)` comprueba posesión vigente de una capacidad exacta. No otorga facultades ni resuelve el reconocimiento de la primera autoridad. Requiere:

1. Cuenta autenticada activa y código presente en el catálogo de hechos.
2. Concesión del actor que abarque el ámbito del recurso.
3. Vigencia de cada eslabón: inicio inclusivo, fin exclusivo y ninguna marca de terminación. Incluso una marca futura se trata como terminación explícita y no como permiso actual.
4. Una raíz de procedencia bootstrap o administrative cuyo UUID pertenezca al conjunto de confianza aportado por el servidor. La palabra bootstrap por sí sola no acredita autoridad; el conjunto está vacío por defecto.
5. En cada delegación: capacidad delegable, origen delegation, padre existente de la misma capacidad, cuenta del padre igual al otorgante del hijo, ámbito contenido e intervalo hijo contenido en el del padre. Un hijo sin fin no cabe bajo un padre con fin.
6. Ausencia de ciclos, referencias faltantes e identificadores duplicados. No basta con que la FK del padre sea válida o que el hijo siga abierto después de revocar al ancestro.

`scope_covers` reconoce global, una organización exacta o un ámbito académico y sus descendientes. El grafo académico debe tener ancestros completos, ser acíclico y conservar la institución en cada enlace. No se mezclan organizaciones con facultades ni se infiere un alcance global de una facultad. Una referencia académica rota se deniega también frente a una concesión global.

Los hechos pueden contener varias concesiones independientes: basta una cadena íntegra y vigente que abarque el recurso. Los errores en una cadena no amplían otra. La definición de confianza inicial y las mutaciones de concesiones siguen pendientes de sus procedimientos PB03/Q05 y SP05; no se fabrica una autoridad para las pruebas de la aplicación real.

## Gobierno y condiciones locales

Las acciones de gobierno se evalúan en contexto personal de la cuenta habilitada. El código de capacidad se vincula explícitamente con los contratos de origen:

| Acción | Capacidad exacta | Ámbito del recurso / referencia |
| --- | --- | --- |
| Gestionar ámbito | academics.scope.manage | Académico; API021 |
| Revisar respaldo personal | academics.verification.review | Académico; API024–026 |
| Solicitar distinción | academics.researcher.request | Académico; API028 |
| Conceder distinción | academics.researcher.award | Académico; API029–030 |
| Revisar organización | organizations.verification.review | Gobierno global; API034–036 |
| Destacar contenido | publications.highlight | Gobierno global; API074 |
| Revisar reporte/revisión | moderation.review | Gobierno global; API078–080/085–087 |
| Aplicar bloqueo | moderation.review | Gobierno global y condiciones PB01/Q07 adicionales |
| Gestionar dominio | academics.domain.manage | Gobierno global; API092–094 |
| Revisar recuperación | identity.recovery.review | Gobierno global; API095–097 |
| Leer auditoría | audit.read | Ámbito real y tipo de decisión expresamente permitido; API098–099 |

El tipo de recurso también debe coincidir. Una capacidad de auditoría sin tipos permitidos se deniega; una concesión académica no permite leer eventos de otra institución. Las futuras consultas deben filtrar antes de paginar y proyectar solo evidencia necesaria; esta función individual no implementa un listado ni autoriza contactos privados como efecto secundario.

Los marcadores siguientes están vacíos por defecto. Son precondiciones técnicas que representarán decisiones documentadas del servidor, no botones de aprobación ni nueva validación institucional:

| Condición pendiente | Rama que exige su configuración |
| --- | --- |
| Q03/Q08: calendario y aviso | Publicar, extender o reactivar una oportunidad. No se calcula aquí un mes ni una nueva fecha. |
| RF45 | Modificar o retirar divulgación; la consulta propia y la publicación inicial siguen separadas. |
| RF59 | Filtro de investigador; la búsqueda ordinaria no lo exige. |
| PB03 | Gestionar ámbitos y dominios reconocidos mediante sus condiciones específicas. |
| Q05 | Solicitar/conceder la distinción con protocolo acreditado. |
| PB06/Q11 | Crear destacado con reglas definidas. |
| PB02/Q13 | Revisión de recuperación excepcional; no bloquea otros caminos de identidad. |
| PB01/Q07 | Interpretación del bloqueo por acción/contexto y vía propia de revisión operativa antes de aplicarlo. |

Una restricción vigente de tipo ban afecta solo a la cuenta, acción exacta y contexto personal/organizacional/both indicados. No se usa coincidencia por prefijos ni comodines. Si falta definir su alcance PB01/Q07, esa operación se deniega indicando la condición; configurado el alcance, se deniega por restricción. Las advertencias, restricciones de otra acción/contexto y medidas vencidas/revocadas no bloquean esa acción.

La lectura pública no recibe un bloqueo global que no se haya acordado. La consulta de la medida propia y la petición de revisión se evalúan antes de restricciones, incluso ante hechos sintéticos que intenten restringirlas. Esto no habilita todavía el procedimiento real de revisión ni permite aplicar un bloqueo antes de que funcione. PB04, decisiones de expedientes, retirada de respaldos, RF45/RF59 y otras condiciones de cada operación conservan su validación funcional pendiente; no se cierran al configurar un marcador.

## Verificación y siguiente incremento

Las pruebas de `backend/modules/access/tests/test_policies.py` usan hechos sintéticos y un instante fijo: matriz de contextos, titularidad, lectura pública y vencimiento, contactos ocultos, representación revocada/reincorporada, privilegios técnicos, delegaciones y ámbitos adversos, límites temporales, condiciones aisladas, revisión propia, auditoría y contratos inmutables. Se comprueba la importación y ejecución con Python `-S`, sin paquetes externos ni configuración Django, y se prohíbe estáticamente leer reloj, entorno o E/S en estas dos unidades.

Comprobación específica: `scripts/probar.ps1 -Modo unitarias backend/modules/access/tests/test_policies.py`. Para una ejecución con evidencias y temporales aislados, añadir `--junitxml` y un `--basetemp` nuevo dentro de `.cache/sprint02`. Flujo general: `scripts/comprobar.ps1 -ConPostgreSQL`. Los resultados exactos, límites y huellas están en [la evidencia de T13](evidencias/politicas-de-acceso.json).

No hay cambios de esquema, migraciones ni filas de negocio añadidas. La siguiente tarea es **SP02-T14: coordinar transacción y auditoría**, mediante casos de muestra que utilicen contratos propietarios y orden estable de bloqueo, con rollback del cambio, la auditoría requerida y la salida pendiente.
