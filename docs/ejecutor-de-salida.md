# Adaptador y ejecutor de salida persistente

SP02-T15 implementa la infraestructura de M09 en el mismo monolito Django: reclamación, preparación, transporte intercambiable, resultado, reintento y recuperación. Corresponde a WI09, DL17, SYS02 y RNF14, con evidencia parcial de AT10/CT11. Reutiliza T34–T36 y las anclas de SP02-T14; no añade tablas, columnas, migraciones, dependencias o un broker.

## Fases y propiedad

`application/delivery/worker.py` coordina `OutboxWorker.run_once`. Las escrituras de T35/T36 están exclusivamente en `modules.notifications.commands.delivery`. M01, M04 y M05 exponen hechos de sus registros mediante selectores propietarios; application no importa modelos ni ejecuta ORM/SQL.

| Fase | Transacción y efecto |
| --- | --- |
| Recuperar | Atomic duradera de M09; bloquea por plazo/UUID, omite filas bloqueadas y cierra reclamaciones vencidas como unknown. |
| Reclamar | Otra atomic duradera: selecciona una intención elegible con SELECT FOR UPDATE SKIP LOCKED, crea intento running y marca processing con plazo. Ambos se confirman juntos. |
| Preparar | Bloquea anclas del origen y después la salida, comprueba posesión de reclamación, relee el sobre y valida el origen/destinatario/payload. Renderiza con una plantilla registrada y vuelve a comprobar tiempo y origen. Confirma antes de retornar el correo preparado. |
| Enviar | Fuera de toda atomic; llama al transporte. Una excepción inesperada se clasifica como resultado incierto, sin guardar su texto. |
| Finalizar | Nueva atomic de M09, con comprobación del UUID/número de intento y plazo; actualiza intento y salida conjuntamente. Un trabajador antiguo no sobrescribe a su sucesor. |

El ejecutor y el adaptador Django rechazan invocarse desde una transacción exterior. Un savepoint interior no sería prueba de commit duradero antes del envío; la muestra de T14 y el ejecutor tienen responsabilidades distintas. No se envía desde señales, on_commit o imports, y el comando no inicia servicios o tareas programadas.

## Reclamación y estados

Una intención pending se reclama solo si no tiene intentos anteriores y está disponible. Una failed puede volver a reclamarse si su último intento fue un fallo temporal explícito, llegó su available_at y no agotó el límite. Sent, cancelled, processing con reclamación vigente y fallos permanentes quedan fuera. Cambiar manualmente una fila a pending con historial no autoriza un reenvío.

La política técnica inicial usa plazo de 120 segundos, máximo de tres intentos y espera exponencial desde 30 segundos, limitada a 3600. Son parámetros de infraestructura del servidor, sustituibles mediante `WorkerPolicy`; no resuelven el calendario ni las condiciones Q03/Q08 de oportunidades. Los contratos rechazan límites ambiguos o desmesurados. El cálculo de espera limita el exponente también ante números de intento muy grandes.

El intento empieza con la reclamación, no acredita que ya se haya llamado al canal. Se numera bajo el bloqueo de la salida. Su UUID, número y lease_until forman la comprobación de generación; el plazo es exclusivo al final. Terminar exige que siga siendo el último intento running y que la misma reclamación continúe vigente. Los contratos retornan proyecciones inmutables, no modelos ORM.

| Resultado observado | T36 | T35 y siguiente acción |
| --- | --- | --- |
| Aceptado por el canal | accepted con fin | sent, sent_at informado, sin reclamación. No acredita entrega en buzón o lectura. |
| Rechazo temporal explícito | failed con código delivery.temporary | failed y nueva disponibilidad; reintento mientras queden intentos. |
| Rechazo permanente | failed con código técnico | failed, retenida sin reintento automático. |
| Desconexión/timeout o resultado incierto | unknown con código técnico | failed, retenida sin reintento automático por defecto. |
| Origen o destinatario inválido | failed con delivery.source_invalid | cancelled; no se llama al transporte. |
| Plantilla desconocida/payload no admitido/renderizado incompatible | failed con código cerrado | failed y retenida; no se llama al transporte. |
| Reclamación perdida o vencida al finalizar | Sin sobrescribir el intento de otro | Resultado del ejecutor stale; la recuperación conserva la incertidumbre. |

Los fallos no se eliminan. El error es un código del catálogo `DeliveryError`, sin mensaje, traceback, credencial, destino o respuesta íntegra del proveedor. La referencia opcional del proveedor admite únicamente UUID opaco, sin reutilizar texto arbitrario. El adaptador SMTP actual no devuelve una referencia de proveedor.

## Origen, privacidad y orden de bloqueo

La pista inicial de origen se lee sin bloquear la salida y se compara de nuevo tras adquirir anclas. Así no se mantiene un bloqueo de T35 mientras se intenta adquirir una cuenta en orden inverso. El orden de preparación es: cuentas por UUID; entidad si corresponde; comprobación u oportunidad; aviso; salida y su intento. Reclamación, recuperación y cierre solo bloquean M09 y no adquieren anclas de otros propietarios.

Para una comprobación de correo se exige cuenta activa y destinatario exacto; snapshot igual al correo actual; finalidad y versión expresamente admitidas por la plantilla; comprobación vigente, no consumida ni invalidada. El payload debe contener exactamente challenge_id. La versión sample-only y las plantillas transaction_sample de T14 se rechazan incluso si se intenta registrarlas para envío.

Para un aviso se exige canal email explícito, programación alcanzada y aviso no cancelado. Su revisión debe seguir siendo la vigente de una oportunidad activa, visible, ya publicada y no vencida. El destinatario será su titular personal o un representante actual de la organización titular verificada; el autor material no basta. El payload admite exactamente notice_id, opportunity_id y validity_revision, esta última como entero. Una FK válida al evento histórico no sustituye estas comprobaciones.

El correo actual del destinatario debe coincidir con el destino almacenado. No se redirige una intención antigua a una nueva dirección por inferencia. No se entregan payloads libres al renderizador: recibe un `DeliveryContext` mínimo con identificadores, finalidad/versión o revisión. La salida preparada contiene asunto/cuerpo/destino solo en memoria, excluidos de repr; no se guardan firmas, enlaces utilizables o contraseñas en T35/T36.

Los futuros escritores de cuenta, respaldo organizacional, representación, origen y aviso deben compartir esas anclas. La comprobación es puntual: no se promete retirar un correo aceptado externamente ni eliminar toda carrera entre el último commit y la aceptación del canal. No existe una transacción atómica que abarque PostgreSQL y SMTP. Las condiciones y procedimientos funcionales pendientes conservan su estado.

## Caídas e incertidumbre

Al vencer una reclamación, la recuperación cierra su intento running como unknown, registra delivery.lease_expired y libera la salida para tratamiento posterior. Si encuentra un estado processing sin intento running coherente, añade una observación unknown con delivery.orphaned; no inventa una aceptación o un envío real. Dos recuperadores usan SKIP LOCKED y no reparan simultáneamente la misma fila.

Una caída puede ocurrir antes de llamar al canal o después de que este acepte y antes de guardar el resultado. Como no siempre se pueden distinguir, la recuperación es conservadora. Un fallo al confirmar la transacción final conserva el intento running y después se recupera como incierto. No se convierte en un fallo temporal seguro que invite a reenviar.

Reintentar unknown exige **ambas** condiciones: política del servidor retry_unknown habilitada y transporte que declare una garantía real de idempotencia. El adaptador SMTP declara supports_idempotency=False; un Message-ID o encabezado estable no garantiza deduplicación. Los transportes de prueba pueden simular una garantía de proveedor, pero no acreditan una de SMTP.

El timeout declarado del transporte debe ser menor que el plazo. En SMTP es un timeout de operación de socket, no una garantía estricta de duración total; pausas del proceso o del canal pueden superar el plazo. Por ello se conserva el resultado incierto, se rechaza la finalización de una generación antigua y no se afirma entrega exactamente una vez.

## Adaptador y entrada operativa

`application/delivery/transports.py` implementa `DjangoEmailTransport`, intercambiable mediante el protocolo `DeliveryTransport`. Acepta un destinatario, texto simple y encabezado X-Entrepares-Outbox con UUID estable; no admite copias o adjuntos arbitrarios. El asunto rechaza saltos de cabecera y el contenido está acotado.

El adaptador admite únicamente los backends Django SMTP y locmem. Los de consola/archivo y otros no reconocidos se rechazan para evitar volcar contenidos privados en registros. Los códigos SMTP 4xx se clasifican como rechazo temporal explícito y los 5xx como permanente; las desconexiones/timeouts conservan incertidumbre. Las pruebas sustituyen la conexión SMTP y emplean memoria: no envían correo real ni acreditan entrega externa.

Entrada: `scripts/django.ps1 deliver_outbox --limit 100`, lote finito de 1 a 1000 pasos. Imprime solo contadores de estados y recuperaciones. Los errores de operación se sustituyen por un mensaje técnico sin parámetros privados; no se imprime el correo preparado o la fila. El comando usa el mismo proyecto Django y su configuración de correo, no otro servicio.

El registro de plantillas del comando está **vacío por defecto**. Cada flujo funcional incorporará expresamente su plantilla, finalidad/versión, renderizado y pruebas al implementar identidad o avisos. Una intención con plantilla desconocida se conserva como fallo permanente y no se envía. Esta decisión evita habilitar firmas, recuperación o política de avisos que aún no están implementadas. Configurar SMTP/remitente y registrar plantillas operativas pertenece a esa integración/despliegue; no se hace un envío real en este incremento.

## Evidencia y siguiente tarea

En desarrollo, `deliver_outbox --limit 1` devolvió empty=1 y recovered=0. La cola estaba vacía; la comprobación conservó el esquema y los datos y no llamó al transporte.

Las pruebas sin base comprueban contratos, límites de política y espera, privacidad de repr, plantillas permitidas, rechazo de cabeceras y clasificación SMTP sin conexión real. Las de PostgreSQL comprueban reclamación duradera visible desde otra conexión antes del transporte, estados/resultados, rechazo de transacciones exteriores, reintentos/límite, origen y destinatario actual, payload mínimo, revisión/canal/representación, pérdida de reclamación, caída y rollback tras aceptación externa.

Los ensayos con conexiones independientes comprueban dos reclamantes, dos ejecutores durante un envío bloqueado, dos recuperadores y cambios de cuenta/vigencia mientras se espera una ancla. Las esperas de origen se observan con pg_blocking_pids. Todas las conexiones de prueba usan test_entrepares y se cierran; se conservan las protecciones de destino y los límites temporales.

Comandos de comprobación: `scripts/probar.ps1 -Modo unitarias backend/application/tests/test_delivery_contracts.py`, `scripts/probar.ps1 -Modo integracion backend/application/tests/test_delivery_postgresql.py` y `scripts/comprobar.ps1 -ConPostgreSQL`. Para conservar resultados, usar `--junitxml` y un `--basetemp` nuevo de `.cache/sprint02`. Las cifras, huellas, límites y estado de desarrollo quedan en [la evidencia de T15](evidencias/ejecutor-de-salida.json).

La siguiente tarea es **SP02-T16: comprobar esquema y datos sintéticos**, contrastando las tablas/campos/FK de referencia. Las plantillas de funciones, el envío externo y el piloto siguen pendientes de sus incrementos.
