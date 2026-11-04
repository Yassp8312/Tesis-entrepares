# Perfiles y formación: T04–T07

Implementación de **SP02-T04**, 4 de noviembre de 2026. M02 (`modules.profiles`) conserva la propiedad del perfil, formación, contactos y méritos declarados. `ProfilesConfig` se incorpora al proyecto Django existente. La referencia es el diccionario lógico v1 y su SQL, identificados en [Base documental](base-documental.json).

## Estructura física

| Tabla | Modelo Django | Columnas | Finalidad |
| --- | --- | --- | --- |
| T04 `profiles_profile` | `Profile` | 9 | Cuenta titular, nombre, presentación, experiencia e intereses declarados. |
| T05 `profiles_education` | `Education` | 8 | Disciplina, institución, condición de estudiante o graduado y finalización de vigencia. |
| T06 `profiles_contact` | `Contact` | 9 | Medio externo, valor, etiqueta, visibilidad dentro de la bolsa y orden. |
| T07 `profiles_merit` | `Merit` | 7 | Título, descripción y fecha opcional del mérito declarado. |

Las **33 columnas** mantienen tipos, nulabilidad y valores predeterminados. `ProfileRecord` es abstracto y comparte UUID y fechas dentro de M02, sin tabla adicional. UUID y fechas tienen valores predeterminados en Django y PostgreSQL; los contactos comienzan con `is_visible=true` y `sort_order=0`. El guardado parcial incorpora `updated_at`; SQL y actualizaciones masivas deben mantenerlo explícitamente cuando corresponda.

`experience_years` utiliza `DecimalField(max_digits=5, decimal_places=1)`, correspondiente a `numeric(5,1)`, y admite ausencia de declaración. Se conservan las [propiedades de precisión y escala de PostgreSQL](https://www.postgresql.org/docs/17/datatype-numeric.html#DATATYPE-NUMERIC-DECIMAL) y su [representación mediante DecimalField](https://docs.djangoproject.com/en/5.2/ref/models/fields/#decimalfield); el formato de entrada se validará en el incremento funcional del perfil.

Las relaciones entre propietarios se declaran con `settings.AUTH_USER_MODEL` y nombres de modelos de M03. M02 no importa sus modelos de negocio. Los registros se representan por UUID, evitando incluir nombre, contacto o relato en su representación habitual.

## Integridad e historial

Se mantienen los **siete CHECK**: nombre no vacío tras `btrim`; experiencia ausente o mayor o igual que cero; condición `student` o `graduate`; contacto de tipo `email`, `phone`, `whatsapp` o `telegram`, valor no vacío y orden no negativo; y título de mérito no vacío.

Las tres reglas de unicidad son:

- `uq_t04_key01 (account_id)`: un perfil por cuenta. La relación ORM usa una FK con esa restricción nombrada, conservando un único índice de soporte.
- `uq_t05_01 (profile_id, discipline_id, institution_id, condition) WHERE ended_at IS NULL`: una sola declaración vigente de la misma combinación. Se admiten varias formaciones distintas e historial finalizado; cerrar una declaración libera esa combinación para una nueva fila.
- `uq_t06_01 (profile_id, kind, value)`: un mismo medio y valor no se repiten dentro de un perfil. La visibilidad no cambia la unicidad; ocultar una fila no permite duplicarla. El mismo teléfono puede declararse como teléfono y WhatsApp, y diferentes perfiles pueden compartir un contacto.

La unicidad de contacto, expresada como índice único en el SQL de referencia, se concreta con una restricción `UNIQUE` y su índice único del mismo nombre. Se mantiene la misma combinación y ausencia de predicado, sin duplicar el índice. La formación utiliza un índice único parcial mediante [`UniqueConstraint.condition`](https://docs.djangoproject.com/en/5.2/ref/models/constraints/#django.db.models.UniqueConstraint.condition). Hay además cuatro índices ordinarios: perfil, disciplina e institución de la formación, y perfil del mérito.

Las **seis FK** (`fk_t04_01`, `fk_t05_01`–`fk_t05_03`, `fk_t06_01`, `fk_t07_01`) conservan `ON DELETE RESTRICT` en PostgreSQL y `models.RESTRICT` en el ORM. Se impide borrar cuentas, perfiles, instituciones o disciplinas con referencias. La migración `profiles/0001_profiles_and_education` depende de identidad inicial y del catálogo académico inicial. Utiliza SQL reversible y `SeparateDatabaseAndState` para conservar nombres, acción SQL y las seis relaciones con `db_constraint=True` al terminar.

La condición pertenece a cada formación. No se añade una clasificación global de «profesional» ni se impone una única formación por persona. Los méritos pueden compartir título y conservan su naturaleza declarada, sin estado de aval o distinción de investigador.

## Completitud, privacidad y alcance posterior

T04 no incorpora indicadores editables de verificado, completo o aparición en bolsa. Conforme a DL02, la completitud se derivará del nombre, una formación vigente con disciplina/institución/condición y al menos un contacto visible. Los perfiles completos se incorporan a la bolsa; el acceso del lector se decide por verificación personal o representación autorizada de organización verificada, además de las restricciones vigentes.

`is_visible` se refiere a la proyección dentro de la bolsa autorizada. Los contactos de T06 se devolverán según lector y visibilidad; la consulta resumida de bolsa no devolverá contactos. Los medios públicos de oportunidades y eventos pertenecen a sus tablas y contratos propios. Al ocultar un contacto, su valor se conserva en la base para el titular; la futura proyección debe excluirlo para quien no tenga acceso.

Esta tarea prepara la persistencia y permite registros todavía incompletos. La validación del conjunto, formatos de los medios externos, al menos un contacto visible y proyecciones autorizadas corresponden a **SP04-T03/T04**, con API012–API015 y el incremento de bolsa correspondiente. No se añade una API en esta tarea de datos ni se declara ejecutada la comprobación de permisos sobre contactos.

El historial de formación se conserva mediante `ended_at`. Cambiar formación no concede ni retira respaldo personal: este pertenece a T12 y a los procedimientos de M03. Los casos funcionales deberán comprobar DL06 junto con sus transacciones y auditoría, sin deducir afiliación verificada de la institución elegida. Las pruebas de esta tarea conservan perfil y cuenta al cambiar una declaración; no acreditan aún una conservación funcional de T12 que sigue pendiente.

La trazabilidad es **WI05, M02, T04–T07, DL02/DL03/DL06, RNF12 y VD18 parcial**. Se acredita la parte física de estas tablas, sin cerrar el esquema completo, el acceso funcional o el piloto.

## Comprobar y aplicar

```powershell
.\scripts\probar.ps1 -Modo integracion backend/modules/profiles/tests/test_profiles_postgresql.py -q
.\scripts\comprobar.ps1 -ConPostgreSQL
.\scripts\django.ps1 migrate --noinput
.\scripts\django.ps1 check --database default --fail-level WARNING
.\scripts\django.ps1 migrate --check
```

Las **64 pruebas nuevas** examinan columnas, tipos y nulabilidad; siete CHECK; claves e índices con sus predicados; seis FK y borrado desde SQL y ORM; valores predeterminados, decimales, fechas y guardado parcial; historial de formación, dimensiones de unicidad, transición sintética a graduado, contactos ocultos y medios compartidos, méritos declarados y rollback de las cuatro tablas.

Tres pruebas transaccionales compiten desde parejas de conexiones PostgreSQL con PID distintos para duplicar perfil, formación vigente y contacto. En cada caso se confirma una inserción y la otra se rechaza por la clave esperada. Las conexiones y esperas están acotadas y se cierran al terminar. Estas carreras de inserción no sustituyen las pruebas futuras de dos ediciones completas con `expected_updated_at`.

La migración se revierte a cero y reaplica únicamente en `test_entrepares`, conservando identidad y catálogos sintéticos y restaurando el grafo completo. El flujo general pasó **433 pruebas del servidor —176 sin base y 257 con PostgreSQL— y 68 del cliente**, sin fallos ni omisiones, además de arquitectura, dependencias/bloqueos, Ruff/formato, tipos, build, Django check, colección y correspondencia de migraciones.

La migración se aplicó a desarrollo: veintidós tablas, 20 migraciones y cero filas en las catorce tablas de negocio implementadas. La base efímera se eliminó al terminar y se conservan las dos persistentes. La evidencia compacta está en [perfiles-y-formacion.json](evidencias/perfiles-y-formacion.json); registros y JUnit permanecen excluidos de Git en `.cache`.
