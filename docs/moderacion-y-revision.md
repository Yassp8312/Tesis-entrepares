# Moderación y revisión: T26–T31

**SP02-T10**, 6 de noviembre de 2026. M07 (`modules.moderation`) incorpora `ModerationConfig` y la persistencia de reportes, decisiones, medidas, restricciones y revisión propia. La referencia es el diccionario lógico v1 y su SQL, identificados en [Base documental](base-documental.json).

## Estructura física

| Tabla | Modelo | Columnas | Responsabilidad |
| --- | --- | --- | --- |
| T26 `moderation_report` | `Report` | 6 | Contenido señalado, autor del reporte y motivo |
| T27 `moderation_decision` | `Decision` | 7 | Resolución inicial, responsable y acción sobre el contenido |
| T28 `moderation_measure` | `Measure` | 11 | Cuenta afectada, decisión de origen, advertencia o bloqueo, intervalo y retiro |
| T29 `moderation_restriction` | `Restriction` | 6 | Capacidad y contexto afectados por una medida |
| T30 `moderation_review_request` | `ReviewRequest` | 5 | Petición motivada de la persona afectada |
| T31 `moderation_review_decision` | `ReviewDecision` | 7 | Ratificación, revocación o sustitución resuelta |

Se conservan **42 columnas, dieciséis CHECK, diez índices no únicos, cinco claves únicas completas y catorce FK nombradas ON DELETE RESTRICT**, no diferibles. Los modelos abstractos no crean tablas. Las representaciones textuales muestran únicamente el UUID. Solo medidas y restricciones tienen `updated_at`, que se actualiza también al guardar parcialmente; no se añade ese campo a los registros que el diseño conserva como evidencia.

La migración `moderation/0001_moderation_and_review` depende de identidad inicial intercambiable, `access/0001_capabilities_and_grants`, `opportunities/0001_opportunities_and_funding` y `publications/0001_publications_events_and_highlights`. Usa SQL reversible y `SeparateDatabaseAndState`: trece relaciones simples quedan con `db_constraint=True` y la relación compuesta de revisión se mantiene explícitamente en PostgreSQL.

## Reporte y decisión inicial

Un reporte debe señalar una oportunidad o una publicación, excluyendo ambos destinos o su ausencia. Conserva el autor y un motivo no vacío tras `btrim`. La cuenta referenciada no demuestra verificación personal: esa condición se comprobará al recibir el reporte. El reporte por una organización mantiene la condición PB05 y no se habilita por este modelo.

El estado abierto o resuelto se deriva de la existencia de su decisión; no se añade un indicador editable. `uq_t27_key01 (report_id)` permite como máximo una resolución inicial. Sus resultados son `violation` y `no_violation`, y las acciones sobre contenido son `none`, `hide` y `remove`. **Una resolución sin infracción solo admite la acción `none`**. El motivo es obligatorio y el responsable queda identificado.

Registrar un reporte conserva el contenido y la habilitación de identidad. La decisión, la eventual medida, el cambio autorizado de visibilidad, la auditoría y la salida persistente deberán coordinarse en los casos de aplicación. La FK de una medida hacia una decisión no prueba que esta confirme infracción ni identifica por sí sola al responsable del contenido; ambas condiciones se comprobarán antes de aplicar la medida. Tampoco se infiere una sanción automática de un contador de reportes.

## Medidas y restricciones

T28 admite `warning` y `ban`. Si existe fin, debe ser posterior al inicio. Una advertencia no admite `ends_at`; un bloqueo puede conservar plazo vacío o uno finito conforme a la política que se configure. El retiro empareja instante y responsable. El historial mantiene la decisión de origen y la cuenta afectada.

El bloqueo no modifica `identity.Account.is_active`. El efecto sobre cada operación corresponde a la autorización vigente, a las restricciones de T29 y al reloj. La elección de duración por administración y el alcance por contexto deben aplicarse según las reglas acordadas; la persistencia no selecciona un plazo ni activa automáticamente el bloqueo.

T29 relaciona medida, capacidad y contexto `personal`, `organization` o `both`. `uq_t29_key01 (measure_id, capability_code, context_kind)` evita duplicados de esa combinación. La capacidad debe existir en el catálogo. **`moderation.request_review` queda excluida expresamente por `ck_t29_02`**, para preservar esa vía al afectado.

Solo un bloqueo podrá recibir restricciones al ejecutar el caso transaccional. La FK de T29 acredita la existencia de la medida, pero no comprueba su clase mediante una condición entre tablas. PB01/Q07 mantienen sus condiciones sobre acciones, contextos y alcance. SP15-T04 exige que la revisión propia esté operativa antes de activar restricciones reales. Este incremento no habilita una rama funcional de bloqueo por disponer de las tablas.

## Revisión propia e historial

La clave `uq_t28_key01 (id, account_id)` soporta:

```text
(measure_id, requested_by) → moderation_measure(id, account_id)
```

**`fk_t30_01` impide pedir revisión de la medida de otra persona**, cambiar al solicitante por otra cuenta o alterar unilateralmente al afectado de una medida que ya tenga solicitudes. Las relaciones ORM `ReviewRequest.measure` y `requested_by` conservan `db_constraint=False` para evitar sustituir la restricción compuesta por referencias simples. La referencia a identidad queda garantizada por la cuenta de la medida y su propia FK. El borrado desde ORM mantiene `models.RESTRICT`.

T30 conserva motivo y fecha. Se admiten varias solicitudes a lo largo de la misma medida; no se introduce una prohibición de revisión adicional por la existencia de una petición anterior. Pendientes, reiteraciones y abuso se controlarán mediante la política del caso.

T31 permite `upheld`, `revoked` y `replaced`. `uq_t31_key01` limita a una decisión por solicitud. El resultado `replaced` exige una medida sustitutiva y los otros resultados la excluyen. `uq_t31_key02` impide reutilizar una misma sustituta en decisiones diferentes; los valores NULL conservan la semántica ordinaria de UNIQUE y permiten distintas resoluciones sin sustitución.

Sustituir deberá comprobar que ambas medidas pertenecen al mismo afectado, revocar la anterior, crear la nueva y conservar la decisión original en una transacción. La FK simple de sustitución no verifica esa coincidencia ni aplica sus efectos. Los registros de reporte, decisión y revisión se tratarán como evidencia por los comandos funcionales, sin ofrecer reescritura del historial; esta migración no añade inviolabilidad frente a acceso ORM/SQL privilegiado.

Los motivos, notas y solicitudes se conservarán en el expediente privado. Las proyecciones públicas no deben incorporarlos por arrastrar relaciones ORM; el registro transversal M10 seguirá usando sus proyecciones mínimas, sin copiar relatos completos. Los lectores autorizados y la consulta de medidas propias se implementarán con sus permisos y filtros correspondientes.

## Comprobaciones y alcance posterior

```powershell
.\scripts\probar.ps1 -Modo integracion backend/modules/moderation/tests -q
.\scripts\comprobar.ps1 -ConPostgreSQL
.\scripts\django.ps1 migrate --noinput
.\scripts\django.ps1 check --database default --fail-level WARNING
.\scripts\django.ps1 migrate --check
```

Las **106 pruebas nuevas de PostgreSQL** cubren esquema, CHECK, claves e índices, catorce FK, borrado SQL/ORM, decisiones compatibles, duración, revisión propia y cambios incompatibles del afectado, protección de la vía de revisión, historial, reemplazo único, valores predeterminados, guardado parcial y rollback del conjunto. Cuatro parejas de conexiones con PID distintos y comienzo sincronizado confirman una inserción y rechazan duplicados de decisión inicial, restricción, decisión de revisión y medida sustitutiva.

La migración se revierte a cero y reaplica exclusivamente en la base efímera, conservando cuentas, capacidades, oportunidad y publicación sintéticas y restaurando el grafo. El flujo general pasó **1052 pruebas del servidor —225 sin base y 827 con PostgreSQL— y 68 del cliente**, sin fallos ni omisiones. También pasaron arquitectura, dependencias/bloqueos, Ruff/formato, tipos, build, Django check, colección y correspondencia de migraciones. Informe privado `.cache/comprobaciones/20261107T045201Z-0ccb6f60/informe.json`.

La ampliación de la suite superó el límite anterior de 300 segundos de integración. Se ajustó exclusivamente esa etapa a 900 segundos y se registró el límite por paso; las demás conservan 300 segundos. El flujo completo se repitió correctamente, manteniendo las protecciones de base y los límites de los casos concurrentes. La explicación del ejecutor está en [Comprobaciones reproducibles](comprobaciones.md).

Tras aplicar la migración, desarrollo conserva cuarenta y dos tablas, 26 migraciones y cero filas en las treinta y cuatro tablas de negocio implementadas. Se mantienen las dos bases persistentes y se eliminó la efímera. La evidencia compacta se registra en [moderacion-y-revision.json](evidencias/moderacion-y-revision.json); los registros privados permanecen en `.cache`.

Trazabilidad: **WI05, M07, T26–T31, DL12/DL13/DL14, RNF12 y VD18 parcial**. SP14 implementará reportes, resolución y consulta autorizada; SP15, revisión y restricciones bajo sus condiciones. SP02-T12 deberá conservar la FK compuesta instalada. Esta tarea mantiene SP02 abierto y aporta pruebas locales sintéticas; los endpoints y resultados del piloto corresponden a sus incrementos posteriores.
