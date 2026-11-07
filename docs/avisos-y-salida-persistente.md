# Avisos y salida persistente: T34–T36

**SP02-T11**, 7 de noviembre de 2026. M09 (`modules.notifications`) incorpora `NotificationsConfig` y la persistencia de programación, intención de envío e intentos observados. La referencia es el diccionario lógico v1 y su SQL, identificados en [Base documental](base-documental.json).

## Estructura e integridad

| Tabla | Modelo | Columnas | Responsabilidad |
| --- | --- | --- | --- |
| T34 `notifications_notice` | `Notice` | 10 | Aviso asociado a una revisión de vigencia de oportunidad |
| T35 `notifications_outbox` | `OutboxMessage` | 15 | Intención persistente, origen, destino, plantilla y procesamiento |
| T36 `notifications_delivery_attempt` | `DeliveryAttempt` | 8 | Número, instantes y resultado observado de cada intento |

Se conservan **33 columnas, quince CHECK, cinco FK nombradas ON DELETE RESTRICT no diferibles, seis índices no únicos y tres reglas de unicidad adicionales a las PK**. Tres de los seis índices no únicos son parciales. El modelo abstracto no crea otra tabla. Aviso y salida tienen fechas de creación y actualización; el intento conserva sus propios instantes de inicio y fin, sin añadir `created_at` o `updated_at` ajenos al diseño. Las representaciones textuales de filas muestran únicamente UUID.

La migración `notifications/0001_notices_outbox_and_attempts` depende de `identity/0002_email_challenge_and_recovery_request`, la cuenta inicial intercambiable y `opportunities/0001_opportunities_and_funding`. Usa SQL reversible y `SeparateDatabaseAndState`: cuatro FK simples terminan con `db_constraint=True` y la referencia compuesta del aviso se mantiene explícita en PostgreSQL.

## Aviso ligado a su revisión

T34 conserva `kind='expiry_reminder'`, revisión positiva e instante programado. La referencia es:

```text
(opportunity_id, validity_revision)
    → opportunities_lifecycle_event(opportunity_id, validity_revision)
```

`fk_t34_01` se apoya en la clave `uq_t19_key01` existente. Rechaza una revisión inexistente o perteneciente a otra oportunidad y cambios incompatibles del evento de origen. La navegación ORM `Notice.opportunity` usa `db_constraint=False`; la integridad hacia la oportunidad se conserva a través del evento y su FK. No se sustituye la relación compuesta por una referencia simple. Al borrar un evento mediante ORM, la restricción compuesta SQL puede producir `IntegrityError`; el colector ORM no representa esa relación como una FK navegable al evento.

`uq_t34_01 (opportunity_id, validity_revision, kind, channel)` trata los NULL como iguales mediante `NULLS NOT DISTINCT`. Así también se impide duplicar un aviso todavía sin canal acordado. Se concreta como restricción UNIQUE e índice del mismo nombre, conservando las columnas, ausencia de predicado y semántica del índice único de referencia. Un aviso cancelado conserva su posición para esa revisión y canal; una revisión nueva puede tener su propio aviso. El índice parcial por `scheduled_for` selecciona avisos sin cancelación.

El canal es opcional y no se decide al preparar la base. Un aviso sin canal no genera por sí mismo un mensaje ni un envío. Canal, destinatarios organizacionales, tolerancia y tratamiento de plazos menores a siete días siguen Q03; calendario y fin de mes mantienen Q08. La regla acordada de avisar siete días antes se integrará con la política de vigencia, no mediante una fecha calculada por defecto en esta migración.

Renovar, cerrar o reactivar requiere invalidar los avisos afectados según el caso. La FK acredita la revisión histórica, pero no demuestra que siga siendo la revisión vigente de T18. Esa comprobación y la cancelación correspondiente pertenecen al caso transaccional y al ejecutor antes de enviar.

## Intención de salida y procesamiento

T35 exige exactamente un origen: aviso o comprobación de correo. La cuenta destinataria es opcional; el destino explícito se conserva como texto. Canal, destino, plantilla y clave de idempotencia deben contener texto tras `btrim`.

`uq_t35_key01 (idempotency_key)` identifica una intención global, incluso si se intenta repetirla con otro origen, canal o destino. La clave se conserva también en estados fallidos, enviados o cancelados. Esta unicidad de intención no demuestra que un proveedor externo acepte una entrega exactamente una vez.

El objeto `payload` toma `{}` por defecto en Python y PostgreSQL. Su CHECK exige un objeto JSON: rechaza listas, escalares y el valor JSON `null`; la columna también rechaza NULL SQL. El CHECK examina estructura, no el significado privado de sus claves o valores. Las interfaces de escritura y las plantillas funcionales deberán construir parámetros mínimos explícitos, evitando serializar modelos o cuerpos HTTP arbitrarios.

La comprobación de correo se referencia por `challenge_id`; **no se debe almacenar en payload un token utilizable, enlace firmado o credencial**. El flujo de identidad deberá revalidar finalidad, destinatario, vigencia y consumo, y obtener la firma al enviar. Esta tarea no implementa la firma, el renderizado ni una garantía semántica de privacidad sobre cualquier JSON insertado directamente por ORM/SQL.

Los estados son `pending`, `processing`, `sent`, `failed` y `cancelled`. `processing` exige `lease_until`; `sent` exige `sent_at` y los demás estados lo excluyen. Los índices parciales seleccionan pendientes/fallidos por disponibilidad y mensajes en proceso por su plazo de reclamación. El esquema no compara esos instantes con «ahora» ni decide cuándo una reclamación está vencida.

El trabajador deberá reclamar con control de concurrencia, revisar origen y destinatario, confirmar el registro persistente correspondiente y ejecutar después el efecto externo. Reclamación, vencimiento, reintento y recuperación de una caída se implementarán con sus transacciones y reloj. Guardar una fila en estas tablas no ejecuta un adaptador ni hace envío de correo.

## Intentos y resultado observado

T36 conserva número positivo por mensaje, instante de inicio, fin opcional, resultado y referencias técnicas opcionales del proveedor. `uq_t36_key01 (outbox_id, attempt_no)` evita números duplicados; la asignación ordenada deberá hacerse bajo bloqueo en el caso de aplicación.

`running` exige fin vacío; `accepted`, `failed` y `unknown` exigen fin informado. Cuando existe, el fin puede coincidir con el inicio o ser posterior. El estado `unknown` permite conservar incertidumbre del adaptador sin inventar una confirmación. Registrar un intento no actualiza automáticamente el estado de salida: la coordinación funcional deberá mantener ambos registros coherentes.

La aceptación por el proveedor no equivale a lectura. Una caída entre aceptación externa y confirmación local puede ocasionar reenvío; ese límite del contrato de entrega se conserva. Errores y referencias del proveedor deberán filtrarse para evitar guardar credenciales o respuestas completas innecesarias.

## Comprobaciones y alcance posterior

```powershell
.\scripts\probar.ps1 -Modo integracion backend/modules/notifications/tests -q
.\scripts\comprobar.ps1 -ConPostgreSQL
.\scripts\django.ps1 migrate --noinput
.\scripts\django.ps1 check --database default --fail-level WARNING
.\scripts\django.ps1 migrate --check
```

Las **80 pruebas nuevas PostgreSQL** cubren esquema, CHECK, índices y unicidad, referencias, revisiones incompatibles y cambios del evento, borrado SQL/ORM restringido, canal NULL, cancelación e historial, orígenes excluyentes, objeto JSON y defaults independientes, estados, instantes, numeración y rollback junto a un cambio de negocio. Cuatro parejas de conexiones con PID distintos y comienzo sincronizado rechazan duplicados de aviso sin canal, aviso con canal, intención e intento.

La migración se revierte a cero y reaplica exclusivamente en la base efímera, conservando cuentas, comprobación, oportunidad y evento de origen y restaurando el grafo. El flujo general pasó **1132 pruebas del servidor —225 sin base y 907 con PostgreSQL— y 68 del cliente**, sin fallos ni omisiones, además de arquitectura, dependencias/bloqueos, Ruff/formato, tipos, build, Django check, colección y correspondencia de migraciones. Informe privado `.cache/comprobaciones/20261107T050856Z-4c18541c/informe.json`.

Tras aplicar la migración, desarrollo conserva cuarenta y cinco tablas, 27 migraciones y cero filas en las treinta y siete tablas de negocio implementadas. Se mantienen las dos bases persistentes y se eliminó la efímera. La evidencia compacta es [avisos-y-salida-persistente.json](evidencias/avisos-y-salida-persistente.json); los registros privados permanecen en `.cache`.

Trazabilidad: **WI05, M09, T34–T36, DL17, RNF12 y VD18 parcial**. SP03 incorporará sus flujos de identidad; SP11, programación, invalidación y recuperación de avisos. SP02-T14 coordinará registros persistentes y efectos obligatorios; SP02-T12 deberá conservar la FK compuesta instalada. Esta tarea mantiene SP02 abierto: prepara datos y pruebas sintéticas, sin acreditar entrega externa ni resultados del piloto.
