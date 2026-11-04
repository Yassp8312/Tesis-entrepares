# Capacidades y delegaciones: T32–T33

Implementación de **SP02-T06**, 4 de noviembre de 2026. M08 (`modules.access`) conserva la propiedad del catálogo de capacidades y las concesiones. Se incorpora `AccessConfig` al monolito Django. La referencia es el diccionario lógico v1 y su SQL, identificados en [Base documental](base-documental.json).

## Modelo físico

| Tabla | Modelo Django | Columnas | Finalidad |
| --- | --- | --- | --- |
| T32 `access_capability` | `Capability` | 3 | Código natural de acción, descripción y posibilidad declarada de delegación. |
| T33 `access_grant` | `Grant` | 16 | Cuenta destinataria, capacidad, contexto, otorgante, origen, vigencia y cierre. |

Las **19 columnas** mantienen tipos, nulabilidad y valores predeterminados. T32 usa `code varchar(80)` como PK y comienza con `is_delegable=false`; no se añade UUID o fecha a esa tabla. En T33, UUID, inicio de vigencia y fechas tienen valores predeterminados de aplicación y base. El guardado parcial incluye `updated_at`; SQL y actualizaciones masivas deben mantenerlo explícitamente cuando corresponda.

`Grant.capability` se almacena en `capability_code`, con referencia a la PK natural de T32. Su atributo ORM `capability_id` contiene el código. Las columnas `granted_by` y `ended_by` conservan sus nombres SQL y se accede a sus identificadores mediante sufijo `_id`. Las relaciones entre propietarios utilizan nombres de modelo y `settings.AUTH_USER_MODEL`, sin importar sus modelos de negocio.

## Restricciones, contexto y cadena

Se conservan **nueve CHECK**: código y descripción no vacíos tras `btrim`; tipos de ámbito y origen admitidos; correspondencia exacta entre tipo y referencias del contexto; prohibición de autorreferencia de concesión; fin de vigencia posterior al inicio cuando existe; fecha y responsable de cierre emparejados; y motivo no vacío al cerrar.

Un contexto global deja vacíos ámbito académico y organización. Un contexto académico exige ámbito y deja vacía organización. Uno organizacional exige organización y deja vacío ámbito. La procedencia admite `bootstrap`, `delegation` y `administrative` como datos de los procedimientos controlados; la aceptación de esos valores por PostgreSQL no habilita su envío desde el navegador.

Las **siete FK** conservan sus nombres y `ON DELETE RESTRICT` real. `fk_t33_07 (parent_grant_id, granted_by) → access_grant (id, account_id)` exige que la concesión fuente pertenezca al otorgante de la nueva concesión. Se rechaza una fuente de otra persona, cambiar el otorgante de un hijo de forma incompatible o cambiar el titular de la fuente ya referenciada. La clave completa `uq_t33_key01 (id, account_id)` soporta esa referencia.

La migración `access/0001_capabilities_and_grants` depende de la cuenta inicial intercambiable, `academics/0002_personal_verifications_and_researcher_awards` y `organizations/0001_organizations_and_representation`. Utiliza SQL reversible y `SeparateDatabaseAndState`: seis relaciones simples quedan con `db_constraint=True`; `parent_grant` conserva `db_constraint=False` en el ORM y su FK compuesta explícita en PostgreSQL. El estado coincide con los modelos y las pruebas inspeccionan las restricciones SQL reales.

## Unicidad y conservación

`uq_t33_01` aplica a `(account_id, capability_code, scope_kind, academic_scope_id, organization_id)` con **`NULLS NOT DISTINCT WHERE ended_at IS NULL`**. Tratar los valores NULL como iguales es necesario porque todos los contextos contienen referencias vacías. Así se evita repetir una concesión abierta en contextos globales, académicos u organizacionales.

Se implementa con [`UniqueConstraint(nulls_distinct=False)` de Django](https://docs.djangoproject.com/en/5.2/ref/models/constraints/#django.db.models.UniqueConstraint.nulls_distinct), soportado por PostgreSQL 17; la semántica está documentada en los [índices únicos de PostgreSQL](https://www.postgresql.org/docs/17/indexes-unique.html). Se verifican `indnullsnotdistinct`, predicado, columnas y rechazo de duplicados en los tres contextos, también desde conexiones simultáneas.

Una concesión con plazo caducado conserva su posición de unicidad mientras `ended_at` siga vacío. La sustitución deberá registrar el cierre y la nueva concesión en su transacción, conservando el historial. El índice no depende del reloj actual. Otras personas, capacidades y contextos pueden tener concesiones independientes. Reabrir un registro histórico se rechaza si esa posición ya está ocupada.

Se conservan siete índices ordinarios, por cuenta, otorgante, responsable de cierre, capacidad, ámbito, organización y fuente/otorgante. Django crea además `access_capability_code_72401c64_like` con `varchar_pattern_ops` al usar `CharField` como PK. Se registra como índice técnico adicional de compatibilidad del framework; no cambia la clave natural, las reglas de unicidad ni el catálogo de permisos. La prueba comprueba su definición y no lo confunde con un índice de negocio del diccionario.

## Autorización y tiempo de operación

La cadena persistida permite comprobar procedencia, pero no demuestra por sí sola que la delegación esté autorizada. Las políticas puras de **SP02-T13** recibirán los hechos actuales desde `application`; la gestión funcional de **SP05-T03** comprobará delegabilidad, autoridad del otorgante, contención del ámbito, ancestros vigentes, límites temporales y ausencia de ciclos de varios nodos. El CHECK de autorreferencia cubre únicamente el ciclo inmediato.

Las reglas que dependen de ahora se evaluarán al operar, conforme a DL20. La base admite intervalos pasados o futuros coherentes sin declarar acceso efectivo por tener una fila. Tampoco se introducen CHECK nuevos que obliguen a una fuente específica a tener padre: la procedencia y sus condiciones pertenecen a los casos de aplicación y los procedimientos acordados.

T32 no se carga con capacidades reales ni se crean concesiones en desarrollo. Poblar ese catálogo no concede permiso. M08 conserva la separación respecto a verificación personal, representación de organizaciones y restricciones de moderación; una concesión aislada no evita esas condiciones. La habilitación inicial protegida SYS03 y las políticas PB03/Q05/Q11 mantienen sus condiciones; API089–API091 se implementarán en sus incrementos. No se infiere autoridad de `is_staff` ni se aceptan `bootstrap` o `administrative` desde una entrada pública por implementar estas tablas.

La trazabilidad es **WI05, M08, T32/T33, DL15/DL20, RNF12 y VD18 parcial**. SP02-T12 deberá conservar la FK compuesta de procedencia al consolidar las restantes.

## Comprobar y aplicar

```powershell
.\scripts\probar.ps1 -Modo integracion backend/modules/access/tests/test_grants_postgresql.py -q
.\scripts\comprobar.ps1 -ConPostgreSQL
.\scripts\django.ps1 migrate --noinput
.\scripts\django.ps1 check --database default --fail-level WARNING
.\scripts\django.ps1 migrate --check
```

Las **70 pruebas nuevas** cubren columnas, PK natural, nueve CHECK, claves e índices, siete FK y sus acciones, valores predeterminados, guardado parcial, ámbitos excluyentes, ventanas temporales, cierre e historial, correspondencia de fuente y otorgante, referencias inexistentes, borrado SQL/ORM y rollback. Tres pruebas sincronizan parejas de conexiones PostgreSQL con PID distintos y confirman una inserción y un rechazo por duplicado para cada tipo de contexto.

La migración se revierte a cero y reaplica solo en `test_entrepares`, conservando datos sintéticos de identidad, ámbito y organización y restaurando el grafo. El flujo general pasó **618 pruebas del servidor —176 sin base y 442 con PostgreSQL— y 68 del cliente**, sin fallos ni omisiones, además de arquitectura, dependencias/bloqueos, Ruff/formato, tipos, build, Django check, colección y correspondencia de migraciones.

El flujo general también se ajusta para pasar `--basetemp` a la integración dentro de su propio directorio de informe. Se comprobó la creación de esa carpeta y la ejecución sin los avisos de limpieza de temporales globales de T05, sin borrar esos directorios ni cambiar la protección de la base de pruebas.

Se aplicó la migración a desarrollo: veintisiete tablas, 22 migraciones y cero filas en las diecinueve tablas de negocio implementadas. La base efímera se eliminó y se conservan las dos persistentes. La evidencia compacta está en [capacidades-y-delegaciones.json](evidencias/capacidades-y-delegaciones.json); registros y JUnit quedan excluidos de Git en `.cache`.
