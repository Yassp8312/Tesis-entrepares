# Coordinación de transacciones y auditoría

SP02-T14 implementa dos casos internos ejecutables de muestra en `backend/application/examples/confirmation.py`. Demuestran la coordinación prevista por WI08/WI09 y DL16/DL18, con evidencia parcial de AT01/AT07 y RNF01/RNF03/RNF06/RNF14. Reutilizan el esquema T02/T35/T37 existente y las políticas puras de M08.

## Casos y propietarios

| Caso | Identidad M01 | Auditoría M10 | Notificaciones M09 |
| --- | --- | --- | --- |
| `prepare_confirmation_example` | Crea metadatos de una comprobación del correo actual de la cuenta, con versión reservada sample-only. | Añade evento mínimo de creación y estado pending, con la correlación de la operación. | Crea una intención pending de plantilla transaction_sample.email_confirmation, con referencias, destino privado y clave de idempotencia de esa salida. |
| `cancel_confirmation_example` | Revalida titularidad, finalidad, versión de muestra, vigencia y ausencia de consumo/invalidación; marca invalidación conservando el origen. | Añade evento de cancelación con estados mínimos pending → cancelled y motivo técnico record_cancelled. | Cancela conjuntamente las salidas de muestra pendientes de esa comprobación; conserva el historial. |

Cada caso abre `transaction.atomic()` y llama a las interfaces propietarias. M01 escribe solo `EmailChallenge`; M10, `AuditEvent`; M09, `OutboxMessage`. `application` no importa modelos ni hace consultas SQL o escrituras ORM. M07 aporta únicamente una proyección mínima de las restricciones de la cuenta; M08 evalúa los hechos recibidos. Ningún módulo escribe registros privados de otro.

Los casos reciben UUID internos del actor y cuenta, un `OperationContext` del servidor y, al preparar, una fecha de vencimiento explícita consciente de zona. La fecha ilustra el contrato interno; no se convierte en un parámetro HTTP libre ni define un plazo definitivo del producto. El perfil, sesión, contraseña, respaldo personal, afiliación y distinción permanecen independientes de estos metadatos.

La correlación se conserva en el recibo y en M10. M09 referencia la misma comprobación de M01; no se añade a T35 una columna de correlación ajena al modelo. El recibo inmutable contiene solo referencias de comprobación, auditoría, salidas y correlación. La cuenta bloqueada y el destino son proyecciones privadas internas con correo excluido de repr; no son respuestas API.

## Autorización y hechos actuales

Las acciones internas `identity.confirmation_sample.prepare` y `identity.confirmation_sample.cancel` requieren cuenta activa, contexto personal y coincidencia exacta de cuenta, recurso y actor. No requieren una verificación personal para gestionar esta comprobación propia. No equivalen a las futuras operaciones HTTP de identidad ni dan autoridad sobre otras cuentas a un superusuario técnico.

El coordinador obtiene el estado actual de M01 bajo bloqueo y lee las restricciones actuales de M07, sin recibir `ActorFacts` ni decisiones previas desde el cliente. M07 devuelve cuenta, código, contexto, intervalo, revocación y condición ban; no motivos, notas o relatos de moderación. M08 comprueba acción/contexto/vigencia con un instante leído después de esperar los bloqueos. Ante una restricción aplicable y PB01/Q07 sin resolver, se deniega esa acción, sin inventar su configuración ni bloquear acciones ajenas.

La cancelación comprueba primero el acceso propio para no abrir una comprobación ajena, bloquea después su origen y salidas y **vuelve a autorizar antes de escribir**. Una espera puede cruzar el inicio temporal de una medida aunque nadie cambie filas. M01 vuelve a comprobar finalidad, versión, consumo, invalidación y vencimiento al ejecutar su transición. No se congelan el reloj o la decisión al comienzo de la operación.

## Orden de bloqueo

El orden de estos casos es:

1. Cuentas que intervienen, UUID ascendente y sin duplicados: `identity.selectors.lock_account_states`.
2. Comprobación de esa cuenta: `identity.selectors.lock_confirmation`, filtrada simultáneamente por cuenta y comprobación.
3. Salidas de esa comprobación, UUID ascendente: `notifications.selectors.lock_confirmation_outbox`.
4. Revalidación final, escrituras propietarias y evento de auditoría dentro de la misma transacción.

Las interfaces de bloqueo rechazan su uso sin una transacción. Los comandos propietarios pueden volver a bloquear los mismos registros ya retenidos: no se adquieren así nuevas anclas en orden inverso. El ejemplo no emplea bloqueos del proceso Python, esperas por sleeps para ordenar la operación ni lecturas de permiso desde una caché.

Esta disciplina es un **contrato que deben respetar los futuros escritores** de los hechos implicados. Las mutaciones de cuenta, restricciones o comprobaciones deben compartir las anclas pertinentes para evitar comprobar un estado que cambie concurrentemente. No se presenta como una protección global frente a SQL directo o futuros comandos que incumplan el orden.

SP02-T15 definirá reclamación y envío. Una fase que solo reclame una salida no debe mantener su bloqueo y luego intentar adquirir una cuenta en orden inverso: tendrá que separar fases y revalidar origen/permiso/destino con el orden acordado. Esta tarea no implementa ni acredita todavía ese ejecutor.

## Atomicidad y errores

Un fallo de cualquier propietario se propaga fuera del bloque atomic. No se captura un error de integridad para continuar dentro de la transacción dañada. Tanto una excepción después de una escritura como un rechazo real de la unicidad de T35 revierten la comprobación, el evento obligatorio y cualquier salida creada. Al cancelar, un fallo devuelve el origen y las salidas a sus valores anteriores y elimina la nueva auditoría; la auditoría inicial se conserva.

La cancelación revisa todas las salidas de su origen antes de modificar el lote. Rechaza un conjunto vacío, una plantilla ajena al ejemplo o estados processing/sent/failed. No intenta retirar un envío que otro ejecutor ya pudo empezar. Si un lote mezcla una salida pendiente con otra incompatible, la operación completa se revierte. Las salidas ya canceladas se conservan; el recibo enumera las pendientes que cambiaron en esa ejecución.

Si el caso se invoca dentro de otra atomic, su éxito solo libera el savepoint interior. La transacción exterior aún puede revertirlo todo; **un recibo retornado no significa que haya un commit duradero**. No se llama manualmente a commit/rollback y no se usa on_commit para simular una cola fiable. La intención persistente pertenece a la transacción de negocio; el efecto externo deberá ocurrir después del commit mediante el ejecutor.

La clave única de T35 identifica una intención para esa comprobación. No representa idempotencia de toda la solicitud de preparación: repetir el caso crea una comprobación nueva. Reintento de una operación completa, deduplicación de peticiones y política de comprobaciones anteriores se concretarán en los flujos funcionales, sin deducirlas de esta unicidad.

## Privacidad y límites del ejemplo

La intención contiene solo `challenge_id` en payload; el destino privado se almacena en su columna propia. No contiene contraseñas, firmas, tokens utilizables, URL de recuperación o documentos. M10 guarda códigos técnicos, UUID y proyecciones cerradas; no copia el correo, snapshot privado, payload, notas o evidencias. El nuevo motivo de cancelación es técnico, no un relato libre.

La versión sample-only y la plantilla transaction_sample.email_confirmation identifican explícitamente estos registros como ejemplos. No se registra una clave de firma o un transporte para ellos. La cancelación tampoco acepta una comprobación de versión operativa como v1. No se generan enlaces, se verifica el correo, se consume la comprobación ni se concede respaldo institucional por crear filas.

No hay ruta HTTP, CLI o tarea programada que invoque estos casos. Las pruebas usan cuentas y destinos sintéticos; desarrollo conserva cero filas de negocio. No se implementan aquí el registro completo, límites de abuso, anti enumeración, firma/consumo, entrega o recuperación excepcional. Las condiciones pendientes PB/Q y los contratos de las operaciones reales conservan su estado. Antes de reutilizar este patrón en una función deberá añadirse su validación de entrada, autorización concreta, transición, controles de concurrencia y pruebas propias.

## Comprobaciones

Las pruebas de `test_transaction_examples.py` comprueban los contratos, referencia propia, contexto, inmutabilidad, ocultación del destino en repr, entradas inválidas y necesidad de transacción. La ampliación del catálogo también entra en la matriz de visitantes y cuentas inactivas de T13. El análisis AST comprueba que el coordinador utiliza interfaces y carece de ORM, SQL, transporte o commit manual; no acredita imports dinámicos o SQL arbitrario.

`test_transaction_examples_postgresql.py` comprueba PostgreSQL real: éxito de ambos casos, referencias/correlación y proyecciones mínimas, fallos después de cada una de las tres escrituras de cada caso, error de integridad real, rollback exterior, permisos y origen ajeno, vigencia/finalidad/versión/consumo, conflictos de salida y lote mixto, y lectura de restricciones actuales. Los ensayos concurrentes usan conexiones con PID distintos, barreras/eventos y límites de bloqueo/consulta; las esperas relevantes se observan con pg_blocking_pids.

Se verifican seis escenarios concurrentes: doble cancelación, cuentas solicitadas en orden inverso, cuenta deshabilitada mientras espera, vencimiento durante la espera, cambio de correo previo a obtener el bloqueo y restricción temporal que entra en vigor mientras espera la salida. El último se reprodujo como fallo antes de añadir la reautorización final y después pasó. Los registros privados de la regresión permanecen en `.cache`, sin incorporarlos al repositorio.

Comandos: `scripts/probar.ps1 -Modo unitarias backend/application/tests/test_transaction_examples.py`, `scripts/probar.ps1 -Modo integracion backend/application/tests/test_transaction_examples_postgresql.py` y `scripts/comprobar.ps1 -ConPostgreSQL`. Para conservar evidencias, usar `--junitxml` y un `--basetemp` nuevo dentro de `.cache/sprint02`. Los resultados y huellas exactos quedan en [la evidencia de T14](evidencias/transacciones-y-auditoria.json).

No se añaden dependencias, modelos o migraciones. La siguiente tarea es **SP02-T15: crear adaptador y ejecutor de salida**, con reclamación, plazo, intentos, reintentos y recuperación de caídas; todavía no se acredita entrega externa ni piloto.
