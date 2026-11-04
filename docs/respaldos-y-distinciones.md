# Respaldos y distinciones: T12–T14

Implementación de **SP02-T05**, 4 de noviembre de 2026. M03 conserva la propiedad de la verificación personal, solicitud de investigador y concesión de la distinción. Se utilizan el diccionario lógico v1 y su SQL, registrados en [Base documental](base-documental.json). El código reutiliza `AcademicRecord`, sin añadir tablas auxiliares ni dependencias.

## Modelo físico

| Tabla | Modelo Django | Columnas | Finalidad |
| --- | --- | --- | --- |
| T12 `academics_personal_verification` | `PersonalVerification` | 13 | Método, solicitud o respaldo, cuenta, origen de correo o ámbito manual y decisión. |
| T13 `academics_researcher_request` | `ResearcherRequest` | 11 | Persona propuesta, ámbito, solicitante, justificación y resolución. |
| T14 `academics_researcher_award` | `ResearcherAward` | 10 | Concesión directa o desde solicitud, autoridad declarada, justificación y finalización. |

Las **34 columnas** conservan tipos, nulabilidad y valores predeterminados. T12 comienza con `status=pending` y T13 con `decision=pending`. Los UUID y fechas mantienen valores de aplicación y base; el guardado parcial conserva `updated_at`. Las columnas `decided_by`, `requested_by`, `awarded_by` y `ended_by` mantienen sus nombres SQL, con sufijo `_id` para obtener su identificador desde el ORM.

## Claves compuestas y referencias

Las **catorce FK** tienen los nombres de referencia y `ON DELETE RESTRICT` real en PostgreSQL. Dos de ellas protegen correspondencias que una relación SQL simple no garantiza:

- `fk_t12_02 (challenge_id, account_id) → identity_email_challenge (id, account_id)`: la comprobación pertenece a la persona verificada.
- `fk_t14_05 (source_request_id, account_id, academic_scope_id) → academics_researcher_request (id, account_id, academic_scope_id)`: la concesión y la solicitud coinciden en persona y ámbito.

Las pruebas rechazan tanto la inserción incompatible como el cambio posterior de cuenta en la comprobación o de persona/ámbito en la solicitud ya referenciada. Las demás FK conservan referencias a cuenta, dominio y ámbito; T12/T14 también las conservan para las vías donde la referencia compuesta no se utiliza.

La migración `academics/0002_personal_verifications_and_researcher_awards` depende de `academics/0001_catalogs_and_scopes` e `identity/0002_email_challenge_and_recovery_request`, además de la cuenta intercambiable. Crea las tablas y añade SQL reversible mediante `SeparateDatabaseAndState`. Las doce relaciones simples terminan con `db_constraint=True`. `PersonalVerification.challenge` y `ResearcherAward.source_request` mantienen `db_constraint=False` en ORM: sus FK compuestas se gestionan explícitamente en SQL. El autodetector confirma la correspondencia con los modelos y las pruebas inspeccionan las restricciones SQL instaladas.

La referencia opcional de T14 permite una concesión directa sin solicitud. Se conserva la semántica `MATCH SIMPLE` de la FK compuesta y la unicidad con valores NULL distintos para `source_request_id`. Las decisiones físicas siguen las [reglas de FK compuestas y valores nulos de PostgreSQL](https://www.postgresql.org/docs/17/ddl-constraints.html#DDL-CONSTRAINTS-FK) y la [separación de estado y SQL de Django](https://docs.djangoproject.com/en/5.2/ref/migration-operations/#separatedatabaseandstate). Antes de alterar estas columnas debe mantenerse explícitamente la integridad compuesta en la migración.

## Restricciones e historial

Se conservan **once CHECK**. T12 admite los métodos `institutional_email` y `manual` y los estados `pending`, `approved`, `rejected`, `withdrawn`. La vía de correo exige comprobación y dominio y deja vacío el ámbito manual; la vía manual exige ámbito y deja vacíos comprobación y dominio. Una petición pendiente no tiene decisor ni fecha; una resolución exige fecha y motivo no vacío. La resolución manual exige además revisor humano. La aprobación automática puede conservar el decisor vacío.

T13 exige justificación, decisión `pending`, `approved` o `rejected`, y revisor, fecha y motivo para una resolución. T14 exige justificación y correspondencia entre fecha y responsable de finalización. Se conservan los CHECK del diseño sin incorporar reglas adicionales de transición o autoridad por inferencia.

Las **dos claves únicas completas** son `uq_t13_key01 (id, account_id, academic_scope_id)`, destino de la FK compuesta, y `uq_t14_key01 (source_request_id)`, que impide utilizar una solicitud para más de una concesión incluso en el historial finalizado. Esta última admite varias concesiones directas con origen NULL.

Los **tres índices únicos parciales** protegen:

- `uq_t12_01 (challenge_id) WHERE challenge_id IS NOT NULL`: una comprobación no se reutiliza en otro expediente de verificación.
- `uq_t12_02 (account_id) WHERE method='manual' AND status='pending'`: una sola petición manual pendiente por persona, incluso entre ámbitos distintos.
- `uq_t14_01 (account_id, academic_scope_id) WHERE ended_at IS NULL`: una sola distinción no finalizada por persona y ámbito.

Los catorce índices ordinarios restantes conservan búsquedas por persona/estado, comprobación/persona, dominio, ámbito, solicitante, revisor, otorgante y origen/persona/ámbito. Se conserva el historial y se permite una nueva petición manual o una nueva concesión cuando se libera su posición vigente. Reutilizar una solicitud de origen sigue limitado por su clave única completa.

## Seguridad y alcance funcional

Las FK demuestran correspondencia de registros; el flujo de correo deberá comprobar firma, finalidad `email_confirmation`, destinatario, dominio exacto reconocido, vencimiento y consumo único, y registrar consumo y respaldo atómicamente. Estas condiciones de DL04 conservan sus incrementos funcionales; no se deducen de la mera existencia de la FK.

Crear una solicitud no concede verificación ni distinción. Resolver T13 deberá coordinarse con T14 cuando corresponda; guardar la resolución por SQL en estas pruebas no ejecuta ese caso. La concesión directa y la revisión manual requieren autoridad vigente y ámbito competente mediante las capacidades de M08. No se infieren facultades de `is_staff`, del correo escrito por el solicitante o de la afiliación declarada.

El respaldo personal, la representación de una entidad y los méritos del perfil permanecen separados. Las pruebas comprueban que cambiar el correo de acceso o retirar el dominio no borra ni modifica automáticamente la fila de respaldo ya almacenada. La conservación del acceso efectivo y el cambio de formación de DL06 se comprobarán con sus selectores y casos funcionales; aquí se acredita la independencia de persistencia.

PB03/Q02 mantienen las condiciones de autoridad y procedimiento de revisión; PB03/Q05, las de distinción. El filtro RF59 conserva su estado propuesto. Las referencias de evidencia y motivos permanecen privados; no se añaden proyecciones HTTP ni auditoría en esta tarea de datos.

La trazabilidad es **WI05, M03, T12–T14, DL04/DL05/DL06, RNF12 y VD18 parcial**. SP02-T12 deberá conservar estas dos FK al consolidar las restantes claves compuestas y vistas.

## Comprobación y reproducción

```powershell
.\scripts\probar.ps1 -Modo integracion backend/modules/academics/tests/test_backing_postgresql.py -q
.\scripts\comprobar.ps1 -ConPostgreSQL
.\scripts\django.ps1 migrate --noinput
.\scripts\django.ps1 check --database default --fail-level WARNING
.\scripts\django.ps1 migrate --check
```

Las **115 pruebas nuevas** examinan esquema, once CHECK, catorce FK y sus acciones, claves e índices, nulabilidad, defaults y fechas parciales; vías manual/correo, decisiones, historial y concesión directa; incompatibilidades de persona/ámbito y modificación de las filas referenciadas; borrado SQL y ORM, rollback conjunto y persistencia independiente del correo/dominio actual.

Cuatro pruebas sincronizan parejas de conexiones PostgreSQL con PID distintos para intentar duplicar una petición manual, una comprobación utilizada, una concesión vigente o una solicitud de origen en el historial. En cada caso se confirma una inserción y se rechaza la otra por la clave esperada, con límites de espera y cierre de conexiones. No sustituyen el consumo firmado ni la resolución concurrente de los casos funcionales.

La migración se revierte a `academics/0001` y reaplica solo en `test_entrepares`, conservando cuenta, comprobación y ámbito sintéticos. La prueba de reversión de identidad también se actualiza para restaurar todas las hojas del grafo y sus tablas, pues ahora este incremento depende de `identity/0002`.

El flujo general pasó **548 pruebas del servidor —176 sin base y 372 con PostgreSQL— y 68 del cliente**, sin fallos ni omisiones. Pasaron arquitectura, dependencias/bloqueos, Ruff/formato, tipos, build, Django check, colección y correspondencia de migraciones. La integración emitió diez avisos de limpieza de antiguos temporales de pytest en Windows, conservados en el registro; no se alteraron esos directorios externos.

Se aplicó la migración a desarrollo: veinticinco tablas, 21 migraciones y cero filas en las diecisiete tablas de negocio implementadas. La base efímera se eliminó y se conservan las dos persistentes. La evidencia compacta está en [respaldos-y-distinciones.json](evidencias/respaldos-y-distinciones.json); registros y JUnit quedan excluidos de Git en `.cache`.
