# Comprobaciones de correo y recuperación: T02/T03

Implementación de **SP02-T01**, 4 de noviembre de 2026. M01 conserva la propiedad de ambas tablas. La fuente es el diccionario lógico v1 identificado en [Base documental](base-documental.json); el SQL de referencia permite conservar los nombres de restricciones. Sus originales permanecen intactos.

## Modelo físico

| Tabla | Modelo Django | Contenido |
| --- | --- | --- |
| T02 `identity_email_challenge` | `identity.EmailChallenge` | Cuenta, finalidad, dirección de entrega concreta, versión de clave, expiración, consumo, invalidación y creación: nueve columnas. |
| T03 `identity_recovery_request` | `identity.RecoveryRequest` | Correo alegado, cuenta identificada cuando proceda, seguimiento privado, alegación, estado, revisor, fecha y motivo de decisión y fechas de mantenimiento: once columnas. |

Los UUID y las fechas de creación tienen valores predeterminados tanto en Django como en PostgreSQL. La recuperación comienza en `pending` y la versión de clave en `v1`. La actualización parcial de una solicitud mediante `save(update_fields=...)` incluye `updated_at`, como ocurre con T01. Las escrituras masivas mediante `update()` o SQL deberán aportar esa fecha explícitamente cuando corresponda; no se añade un disparador.

`decided_by` conserva exactamente ese nombre de columna. En el ORM, la relación es `decided_by` y su UUID se obtiene como `decided_by_id`. La cuenta afectada usa `account_id` en ambas tablas. Los modelos se representan por UUID, sin incluir el relato ni el contacto privado en su representación habitual.

## Integridad implementada

T02 conserva `ck_t02_01`–`ck_t02_05`: admite únicamente `email_confirmation` y `password_reset`, exige dirección y versión de clave no vacías, exige expiración posterior a creación y prohíbe consumo e invalidación simultáneos. El índice `ix_t02_01` ordena cuenta, finalidad y expiración. `uq_t02_key01 (id, account_id)` prepara el destino de la FK compuesta de T12; la referencia T12 se incorporará en SP02-T05.

T03 conserva `ck_t03_01`–`ck_t03_05`: estados `pending`, `approved` y `rejected`, correo alegado y relato no vacíos, decisión pendiente sin revisor ni fecha, decisión resuelta con revisor, fecha y motivo no vacío, y cuenta identificada obligatoria para aprobar. Un rechazo puede conservar la cuenta sin identificar. Los índices son `ix_t03_01 (account_id)` e `ix_t03_02 (decided_by)`.

Las tres FK (`fk_t02_01`, `fk_t03_01`, `fk_t03_02`) apuntan a T01 y usan **`ON DELETE RESTRICT` en PostgreSQL**, además de `models.RESTRICT` en Django. No se generan índices simples redundantes para las relaciones.

La migración `identity/0002_email_challenge_and_recovery_request` crea primero las tablas sin FK automáticas y luego usa `SeparateDatabaseAndState`: añade el SQL de las FK con sus nombres y mantiene las relaciones con `db_constraint=True` en el estado final de Django. Sus operaciones inversas retiran las FK antes de retirar las tablas. Esto evita depender de los nombres generados por Django o confundir su comportamiento de borrado en Python con la acción SQL. El autodetector confirma que el estado final coincide con los modelos.

La documentación de Django aclara que [`on_delete` no crea una acción SQL de borrado](https://docs.djangoproject.com/en/5.2/ref/models/fields/#django.db.models.ForeignKey.on_delete). La separación controlada de estado y SQL utiliza la operación oficial [`SeparateDatabaseAndState`](https://docs.djangoproject.com/en/5.2/ref/migration-operations/#separatedatabaseandstate). PostgreSQL documenta las [restricciones referenciales y `RESTRICT`](https://www.postgresql.org/docs/17/ddl-constraints.html#DDL-CONSTRAINTS-FK).

## Seguridad y alcance funcional

T02 guarda metadatos, nunca un token utilizable, clave de firma o contraseña. T03 conserva una alegación privada; no obtiene automáticamente la cuenta comparando el correo ni acredita el contacto aportado. Crear una fila o marcarla como aprobada en una prueba de persistencia no crea sesión, cambia contraseñas ni concede permisos.

Esta tarea no añade entradas HTTP, envíos ni escrituras de auditoría. T37 se implementará en SP02-T07. La exclusión de contraseñas y enlaces firmados de las proyecciones de auditoría deberá comprobarse de nuevo al implementar los casos funcionales; aquí no se declara probada una auditoría que todavía no existe.

Se conservan los CHECK de referencia, sin introducir reglas nuevas por inferencia. La base garantiza la coherencia de cada fila; comprobar firma, destinatario, finalidad, vencimiento en el momento de uso, consumo único frente a concurrencia, transiciones autorizadas y revisión competente requiere comandos y coordinación transaccional posteriores. Tampoco se fija una duración de enlace a partir de la hora usada por las pruebas. PB02/Q13 siguen condicionando la recuperación sin acceso al correo.

La trazabilidad de planificación es **WI05, M01, T02/T03, DL04/DL18, RNF12 y VD18**. Este incremento acredita la parte física de T02/T03 y prepara su futura integración; no cierra WI05, las 37 tablas ni la totalidad de DL04/DL18 o VD18.

## Comprobación y reproducción

```powershell
.\scripts\probar.ps1 -Modo integracion backend/modules/identity/tests/test_recovery_metadata_postgresql.py -q
.\scripts\comprobar.ps1 -ConPostgreSQL
.\scripts\django.ps1 migrate --noinput
.\scripts\django.ps1 check --database default --fail-level WARNING
.\scripts\django.ps1 migrate --check
```

Las **42 pruebas nuevas** ejecutan SQL real sin depender de validadores del ORM: comprueban columnas, tipos, nulabilidad, diez CHECK, tres FK y su acción, índices, clave compuesta, valores predeterminados, dirección de entrega conservada, estados terminales, decisiones, borrado impedido desde SQL y ORM, actualización parcial y rollback conjunto. Una tabla sintética creada dentro de la transacción de prueba acredita la referencia compuesta a T02 y rechaza una cuenta incompatible; no sustituye las pruebas futuras de T12.

Otra prueba revierte `0002` a `0001` y vuelve a aplicarla en `test_entrepares`, conservando una cuenta sintética y comprobando las restricciones restauradas. El destino se protege con los controles existentes; no se ensaya la reversión sobre desarrollo.

El flujo completo pasó **237 pruebas de servidor: 176 sin base y 61 con PostgreSQL**, y **68 del cliente**, sin fallos ni omisiones. También pasaron arquitectura, bloqueos, dependencias, Ruff/formato, tipos, build, comprobación de Django, colección y correspondencia entre modelos y migraciones.

La base local pasó de nueve a once tablas y de 16 a 17 migraciones aplicadas. Las tres tablas de identidad permanecen sin filas de prueba. Se conservan las dos bases persistentes y se elimina la efímera al terminar. La evidencia compacta está en [comprobaciones-y-recuperacion.json](evidencias/comprobaciones-y-recuperacion.json); informes y registros detallados quedan excluidos de Git en `.cache`.
