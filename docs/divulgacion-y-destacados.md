# Divulgación y destacados: T23–T25

**SP02-T09**, 6 de noviembre de 2026. M06 (`modules.publications`) incorpora `PublicationsConfig` y la persistencia de novedades, eventos y selección de contenido destacado. La referencia es el diccionario lógico v1 y su SQL, identificados en [Base documental](base-documental.json).

## Estructura e integridad

| Tabla | Modelo | Columnas | Responsabilidad |
| --- | --- | --- | --- |
| T23 `publications_publication` | `Publication` | 13 | Titular, autor material, clase, texto, estado editorial y visibilidad |
| T24 `publications_event_detail` | `EventDetail` | 12 | Fecha, hora opcional, zona, modalidad y vía externa de participación |
| T25 `publications_highlight` | `Highlight` | 11 | Contenido seleccionado, responsable, fuente, intervalo y retiro |

Se conservan **36 columnas, veinte CHECK, diez índices no únicos, una clave única completa y dos índices únicos parciales**, además de las PK. Hay nueve FK nombradas `ON DELETE RESTRICT` no diferibles: ocho simples y una compuesta. Los modelos abstractos comparten UUID y fechas sin crear otras tablas. T24 usa `publication_id` como PK, sin identificador adicional. Las representaciones textuales de filas muestran únicamente su UUID.

La migración `publications/0001_publications_events_and_highlights` depende de la cuenta inicial intercambiable, `organizations/0001_organizations_and_representation`, `opportunities/0001_opportunities_and_funding` y `access/0001_capabilities_and_grants`. Conserva nombres y acciones SQL con operaciones reversibles y `SeparateDatabaseAndState`. Las ocho FK simples terminan con `db_constraint=True` en el ORM.

## Publicaciones y eventos

T23 exige un titular personal o una organización, excluyendo ambos o ninguno; mantiene independiente al autor material. La publicación organizacional no referencia la representación que permitió crearla. Una revocación conserva contenido y autoría. La autoridad para publicar o gestionar por el titular se comprobará al ejecutar el caso de aplicación.

`kind` admite `news` y `event`. `status` distingue `draft`, `published` y `withdrawn`; `visibility` distingue `visible`, `hidden` y `removed`. El estado editorial y la moderación son dimensiones independientes. El texto y título no pueden quedar vacíos después de `btrim`; fuera de borrador técnico se exige fecha de publicación. `row_version` es positiva. La comprobación e incremento de versión frente a ediciones simultáneas se implementarán con los comandos funcionales.

El detalle T24 se vincula mediante:

```text
(publication_id, publication_kind) → Publication(id, kind)
publication_kind = 'event'
```

`uq_t23_key01 (id, kind)` soporta esa FK. **La base impide asociar un detalle a una novedad**, reasignarlo a una novedad o convertir su publicación en `news` mientras conserve el detalle. La relación navegable ORM `EventDetail.publication` usa `OneToOneField(db_constraint=False)`; la restricción compuesta `fk_t24_01` se mantiene explícitamente en PostgreSQL. No se añade una FK simple que oculte esa condición.

Publicar un evento exigirá crear o validar su detalle en la misma transacción. La FK protege el tipo del padre, pero no obliga por sí sola a que toda publicación `event` tenga un detalle durante una preparación intermedia. El cambio de tipo deberá gestionar el detalle de forma coherente; el formato HTTP y sus permisos siguen los contratos aprobados.

T24 conserva una fecha sin inventar una hora: `start_time` es opcional y `time_zone` toma `America/Havana` por defecto. Las modalidades son presencial, en línea e híbrida. El lugar puede omitirse; si se aporta, debe contener texto. Se exige URL externa, contacto público propio o ambos. Tipo y valor de contacto aparecen juntos, con correo, teléfono, WhatsApp o Telegram como tipos admitidos. Las vías y la zona deben contener texto; la validación de esquema URL, canal y zona válida pertenece a la entrada funcional de SP12.

El contacto del evento es un valor propio, sin FK a contactos privados de perfil. Ocultar, cambiar o borrar un contacto del perfil no altera esa vía pública. Los campos permiten comunicar participación mediante un enlace o contacto externo; las proyecciones públicas y su filtrado se implementarán en sus casos de consulta.

## Destacados e historial

T25 exige exactamente una oportunidad o una publicación como destino. Conserva quién concedió el destacado y la concesión de capacidad usada, cuando corresponda. Esa referencia no acredita por sí sola que el responsable tenga autoridad, que la capacidad sea adecuada o que la fuente siga vigente: `application` deberá evaluar esos hechos al ejecutar la selección.

El intervalo puede tener fin vacío; cuando existe, debe ser posterior al inicio. El retiro empareja instante y responsable. Los índices `uq_t25_01` y `uq_t25_02` permiten como máximo un registro **sin retirar** para cada oportunidad o publicación. Un registro cuyo plazo terminó sigue ocupando esa posición hasta registrar su retiro. Para sustituirlo se conservará la fila anterior y se cerrará su condición antes de insertar la nueva, en una transacción.

La selección efectiva se comprobará contra el reloj y la visibilidad del destino; las condiciones relativas a la fuente se concretarán con Q11/PB06. Los índices parciales se basan en retiro y destino, sin depender de «ahora». Duración, límites y orden siguen Q11; esta tarea no fija una duración predeterminada ni habilita facultades por el hecho de almacenar un destacado.

Las nueve FK restringen borrados accidentales de cuentas, organizaciones, publicaciones, oportunidades y concesiones referenciadas. La ocultación y el retiro usan estados y conservan registros. Los cambios parciales ORM actualizan `updated_at` sin alterar `created_at`. Se preserva el índice de orden `published_at DESC, id` y las búsquedas por titular, autor, destino, responsable y fuente.

## Comprobaciones y alcance

```powershell
.\scripts\probar.ps1 -Modo integracion backend/modules/publications/tests -q
.\scripts\comprobar.ps1 -ConPostgreSQL
.\scripts\django.ps1 migrate --noinput
.\scripts\django.ps1 check --database default --fail-level WARNING
.\scripts\django.ps1 migrate --check
```

Las **107 pruebas nuevas de PostgreSQL** cubren columnas, CHECK, índices, FK, borrado SQL/ORM, separación de titular y autor, estados, fecha de publicación, integridad de la FK compuesta, modalidades, hora opcional, vías externas, contactos independientes, fuentes, intervalos, retiro e historial, valores predeterminados, guardado parcial y rollback del conjunto. Dos parejas de conexiones con PID distintos y comienzo sincronizado confirman una inserción y rechazan su duplicado para destacados de oportunidad y publicación.

La migración se revierte a cero y reaplica solo en la base efímera, conservando cuenta, entidad, oportunidad y concesión sintéticas y restaurando el grafo. El flujo general pasó **946 pruebas del servidor —225 sin base y 721 con PostgreSQL— y 68 del cliente**, sin fallos ni omisiones. También pasaron arquitectura, dependencias/bloqueos, Ruff/formato, tipos, build, Django check, colección y correspondencia de migraciones. Informe privado `.cache/comprobaciones/20261107T042714Z-78636888/informe.json`.

Tras aplicar la migración, desarrollo conserva treinta y seis tablas, 25 migraciones y cero filas en las veintiocho tablas de negocio implementadas. Se mantienen las dos bases persistentes y se eliminó la efímera. La evidencia compacta se registra en [divulgacion-y-destacados.json](evidencias/divulgacion-y-destacados.json); los registros privados permanecen en `.cache`.

Trazabilidad: **WI05, M06, T23–T25, DL01/DL11/DL12, RNF12 y VD18 parcial**. SP12 implementará publicación y consulta de divulgación; SP13-T03, la gestión autorizada de destacados. RF45 conserva su carácter propuesto para edición/retirada propia y Q11/PB06 mantienen sus condiciones. Los estados técnicos no las aprueban por inferencia. Esta tarea prepara datos, sin incorporar endpoints ni resultados del piloto, y mantiene SP02 abierto. SP02-T12 deberá conservar la FK compuesta ya instalada.
