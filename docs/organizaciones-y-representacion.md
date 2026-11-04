# Organizaciones y representación: T15–T17

Implementación de **SP02-T03**, 4 de noviembre de 2026. M04 conserva la propiedad de las entidades, expedientes y autorizaciones. Se incorporó `OrganizationsConfig` al proyecto Django existente, manteniendo el monolito modular. El diccionario lógico v1 y su SQL de referencia son las fuentes identificadas en [Base documental](base-documental.json).

## Modelo físico

| Tabla | Modelo Django | Columnas | Finalidad |
| --- | --- | --- | --- |
| T15 `organizations_organization` | `Organization` | 8 | Identidad de la entidad, tipo, presentación, creador y vínculo opcional con una institución. |
| T16 `organizations_verification` | `OrganizationVerification` | 10 | Solicitud, estado de revisión, referencia privada y metadatos de resolución. |
| T17 `organizations_representation` | `Representation` | 9 | Cuenta autorizada, otorgante, revocación y conservación de la autorización histórica. |

Se conservan las **27 columnas** del diseño, con sus tipos, nulabilidad y valores predeterminados. `OrganizationRecord` comparte UUID y fechas como modelo abstracto exclusivo de M04; no crea otra tabla. UUID, creación y actualización inicial tienen valores predeterminados tanto en la aplicación como en PostgreSQL. Las solicitudes comienzan en `pending`.

Los nombres SQL `created_by`, `requested_by`, `decided_by`, `granted_by` y `revoked_by` se conservan. En el ORM son relaciones y sus identificadores usan el sufijo `_id`. Las referencias entre propietarios se declaran mediante nombres de modelo y `settings.AUTH_USER_MODEL`; el código de negocio no importa modelos de M01 o M03.

## Restricciones e historial

Los **siete CHECK** de referencia protegen los nombres y tipos de entidad; los estados `pending`, `approved`, `rejected`, `withdrawn`; la coherencia de la decisión; la correspondencia entre fecha y responsable de revocación; y una revocación que no sea anterior a la creación de la autorización.

Una solicitud pendiente conserva revisor y fecha vacíos. Resolverla exige fecha, revisor y motivo no vacío tras `btrim`. La referencia privada de evidencia mantiene su nulabilidad de diseño: su exigencia por procedimiento no se sustituye por un CHECK nuevo. La causa de revocación también conserva su nulabilidad física; el contrato funcional de revocación deberá exigir el motivo correspondiente.

Dos índices únicos parciales aplican las reglas de historial:

- `uq_t16_01 (organization_id) WHERE status = 'pending'`: una sola solicitud pendiente por organización, independientemente de quién la presente. Resolverla permite otra solicitud y conserva los expedientes anteriores.
- `uq_t17_01 (organization_id, account_id) WHERE revoked_at IS NULL`: una sola autorización sin revocar por pareja. Puede conservarse más de una autorización revocada y concederse otra nueva. Una cuenta puede representar varias organizaciones y una organización puede tener varias cuentas representantes.

Las condiciones se declaran con [`UniqueConstraint.condition` de Django](https://docs.djangoproject.com/en/5.2/ref/models/constraints/#django.db.models.UniqueConstraint.condition) y se materializan como [índices parciales de PostgreSQL](https://www.postgresql.org/docs/17/indexes-partial.html). No se hace una comprobación previa de existencia como sustituto de la unicidad de base. Las pruebas inspeccionan los predicados y también compiten desde dos conexiones.

Se mantienen diez índices ordinarios: búsqueda de entidades por `lower(name)`, institución y creador; verificaciones por entidad/estado, solicitante y decisor; y representaciones por entidad, cuenta, otorgante y revocador. Los nombres de entidades no son únicos globalmente.

Las **nueve FK** (`fk_t15_01`–`fk_t15_02`, `fk_t16_01`–`fk_t16_03`, `fk_t17_01`–`fk_t17_04`) tienen `ON DELETE RESTRICT` en PostgreSQL y `models.RESTRICT` en Django. Se conservan las cuentas, instituciones, entidades e historial referenciados frente a borrados accidentales. La migración `organizations/0001_organizations_and_representation` depende de la cuenta inicial y del catálogo académico inicial; utiliza SQL reversible y `SeparateDatabaseAndState` para conservar nombres y acción SQL, con las nueve relaciones en `db_constraint=True` al terminar.

## Seguridad y alcance posterior

T15 no incorpora una bandera de organización verificada ni crea una representación por guardar su creador. Vincular una institución de catálogo tampoco verifica la entidad. T17 no contiene rangos entre representantes ni un campo de verificación personal: el acceso organizacional deberá comprobar organización verificada y representación vigente, sin exigir respaldo personal a esa cuenta, conforme a DL07 y los contratos aprobados.

Este incremento prepara la persistencia. No añade endpoints, concede capacidades M08, ejecuta reuniones de revisión o decide la verificación efectiva. Las pruebas de decisiones e incorporaciones escriben datos sintéticos para comprobar integridad; no acreditan una revisión institucional.

La verificación de universidades conserva el procedimiento de reunión con decano; la de privados, reunión y documentación. El procedimiento de `state_other` y la retirada del respaldo conservan su condición pendiente. El primer y último representante y la recuperación de entidad mantienen PB04. Los casos funcionales deberán coordinar autoridad, revisión, vigencia, revocación frente a publicación y auditoría, conservando los contenidos de la organización; las tablas de contenidos y auditoría se incorporan en sus tareas.

El guardado parcial mediante `save(update_fields=...)` mantiene `updated_at`. SQL y escrituras masivas deberán aportar su actualización cuando corresponda. Las restricciones garantizan filas e historial coherentes; las transiciones autorizadas y los efectos sobre otros módulos pertenecen a la coordinación de aplicación.

La trazabilidad es **WI05, M04, T15–T17, DL07/DL19, RNF12 y VD18 parcial**. No se cierra el esquema completo, el acceso funcional ni el piloto.

## Pruebas y reproducción

```powershell
.\scripts\probar.ps1 -Modo integracion backend/modules/organizations/tests/test_organizations_postgresql.py -q
.\scripts\comprobar.ps1 -ConPostgreSQL
.\scripts\django.ps1 migrate --noinput
.\scripts\django.ps1 check --database default --fail-level WARNING
.\scripts\django.ps1 migrate --check
```

Las **69 pruebas nuevas** examinan esquema real, valores predeterminados, guardado parcial, siete CHECK, doce índices incluidos los dos parciales, nueve FK, referencias inexistentes, borrado restringido desde SQL y ORM, decisiones completas, homónimos, independencia del respaldo personal, historial y rollback conjunto. Se comprueba que un expediente resuelto o una autorización revocada no puedan volver a ocupar una posición vigente ya utilizada.

Dos pruebas transaccionales usan sendas parejas de conexiones PostgreSQL independientes, sincronizadas antes de insertar. En cada caso se confirma una fila y la otra inserción se rechaza por el índice único esperado. Las conexiones tienen límites de espera y se cierran al terminar. Esto acredita las carreras de inserción de T16/T17; no sustituye las futuras pruebas de revocación concurrente con publicación.

La migración se revierte a cero y reaplica en `test_entrepares`, conservando una cuenta y una institución sintéticas, y comprobando las FK e índices restaurados. Al introducir esta dependencia de M03, se ajustó su prueba de reversión para restaurar todas las hojas del grafo de migraciones; así también restituye los módulos que dependen de los catálogos.

El flujo general pasó **369 pruebas de servidor —176 sin base y 193 con PostgreSQL— y 68 del cliente**, sin fallos ni omisiones. Pasaron también arquitectura, dependencias/bloqueos, Ruff/formato, tipos, build, Django check, colección y correspondencia entre modelos y migraciones. La migración se aplicó a desarrollo: dieciocho tablas, 19 migraciones y cero filas en las diez tablas de negocio implementadas. La base efímera se eliminó al terminar; se mantienen las dos persistentes.

La evidencia compacta está en [organizaciones-y-representacion.json](evidencias/organizaciones-y-representacion.json); registros y JUnit se conservan fuera de Git en `.cache`.
