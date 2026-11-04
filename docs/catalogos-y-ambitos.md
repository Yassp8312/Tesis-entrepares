# Catálogos y ámbitos académicos: T08–T11

Implementación de **SP02-T02**, 4 de noviembre de 2026. El propietario es M03 (`modules.academics`). Se utiliza el diccionario lógico v1 y su SQL de referencia, identificados en [Base documental](base-documental.json). La aplicación se incorpora a los ajustes de Django; no se añade una segunda aplicación desplegable ni un servicio.

## Estructura física

| Tabla | Modelo | Columnas | Función |
| --- | --- | --- | --- |
| T08 `academics_institution` | `Institution` | 7 | Instituciones declarables, clasificación y origen de la entrada. |
| T09 `academics_scope` | `AcademicScope` | 7 | Ámbitos jerárquicos pertenecientes a una institución. |
| T10 `academics_discipline` | `Discipline` | 6 | Carreras o disciplinas curadas o declaradas. |
| T11 `academics_domain` | `InstitutionalDomain` | 9 | Dominio institucional exacto, estado de revisión y referencia privada de respaldo. |

Las 29 columnas conservan tipos, nulabilidad y valores predeterminados del diseño. `AcademicRecord` es un modelo abstracto interno de M03 que comparte UUID y fechas; no crea una quinta tabla. Los UUID y las fechas tienen valores predeterminados de aplicación y base. El dominio comienza en `pending`. El guardado parcial mediante `save(update_fields=...)` mantiene `updated_at`; SQL y actualizaciones masivas deben aportar la fecha cuando proceda.

Las columnas `created_by` y `decided_by` mantienen esos nombres SQL. En el ORM son relaciones cuyo UUID se obtiene como `created_by_id` y `decided_by_id`. Las referencias a cuentas utilizan `settings.AUTH_USER_MODEL`, sin importar modelos de M01 en el código de negocio de M03.

## Restricciones y relaciones

Se conservan los **doce CHECK** de referencia: nombre no vacío tras `btrim`, clasificaciones y orígenes admitidos, prohibición de padre igual al propio ámbito, dominio no vacío y en minúsculas sin espacios exteriores, estados admitidos y revisión completa para reconocer o retirar un dominio. Una resolución de dominio exige revisor, fecha y referencia de evidencia no vacía. El estado `pending` conserva las posibilidades del esquema original, sin añadir por inferencia un CHECK que le prohíba esos metadatos.

Las instituciones y disciplinas admiten homónimos y variantes de escritura: no se fuerza una equivalencia por nombre. Hay ocho índices: búsqueda por `lower(name)` en ambos catálogos, sus creadores, institución y padre de los ámbitos, e institución y revisor de los dominios. Las claves únicas son `uq_t09_key01 (id, institution_id)` y `uq_t11_key01 (domain_ascii)`.

Las **seis FK** tienen sus nombres `fk_t08_01`, `fk_t09_01`, `fk_t09_02`, `fk_t10_01`, `fk_t11_01` y `fk_t11_02`, con `ON DELETE RESTRICT` real en PostgreSQL. Se impide borrar un creador, revisor, institución o padre mientras existan las referencias correspondientes.

`fk_t09_02 (parent_id, institution_id) → academics_scope (id, institution_id)` impide elegir un padre de otra institución. También impide cambiar unilateralmente la institución de un padre que tiene hijos. Un ámbito raíz conserva `parent_id = NULL`, admitido por la semántica `MATCH SIMPLE` de la FK y la institución obligatoria.

La migración inicial `academics/0001_catalogs_and_scopes` crea las tablas y aplica SQL reversible para las FK. `SeparateDatabaseAndState` sincroniza las cinco relaciones simples como `db_constraint=True`. `AcademicScope.parent` mantiene `db_constraint=False` en el modelo y el estado: Django gestiona su navegación y borrado en el ORM, mientras la FK SQL compuesta garantiza la correspondencia institucional. No se sustituye esa FK por una relación SQL simple ni se utiliza una API interna de Django para simularla. Antes de cambiar estas columnas, habrá que mantener explícitamente la restricción compuesta en la migración; el autodetector no conoce su composición.

Este mecanismo sigue la [documentación de `ForeignKey.db_constraint`](https://docs.djangoproject.com/en/5.2/ref/models/fields/#django.db.models.ForeignKey.db_constraint), la [separación de estado y SQL en migraciones](https://docs.djangoproject.com/en/5.2/ref/migration-operations/#separatedatabaseandstate) y las [FK compuestas y autorreferencias de PostgreSQL](https://www.postgresql.org/docs/17/ddl-constraints.html#DDL-CONSTRAINTS-FK). Las pruebas inspeccionan la FK compuesta instalada, además de comprobar la correspondencia del estado ORM con los modelos.

## Alcance de seguridad y tareas posteriores

Una entrada de catálogo no es una organización verificada, una afiliación comprobada ni una concesión de capacidad. Ninguna de estas tablas concede privilegios a su creador o revisor. T11 conserva una referencia privada, que no se incorpora a un catálogo público. La carga inicial de instituciones y disciplinas reales revisadas pertenece a SP18-T05; estas comprobaciones usan exclusivamente datos sintéticos.

El CHECK de T09 evita la autorreferencia inmediata. Los ciclos entre varios ámbitos requieren recorrido y coordinación de aplicación, previstos expresamente en **SP05-T02** junto con las operaciones API020/API021. El esquema actual no acredita esa protección completa ni resuelve la autoridad inicial de PB03.

T11 exige la forma almacenada en minúsculas y sin espacios exteriores; la conversión a ASCII, validación de sintaxis DNS y comparación del dominio exacto del correo deberán incorporarse al flujo funcional correspondiente. La base no hace búsquedas por sufijo ni extiende el reconocimiento a un subdominio por inferencia. Retirar el dominio tampoco modifica por sí mismo una verificación personal: T12 y sus operaciones se implementan en sus tareas.

Se aporta evidencia física a **WI05, DL05/DL20, RNF12 y VD18**. Las operaciones de gobierno, autorización, auditoría y evaluación del piloto conservan su alcance posterior. SP02-T12 deberá consolidar las demás FK compuestas y vistas, conservando la FK de padre ya creada en esta tarea.

## Comprobar y aplicar

```powershell
.\scripts\probar.ps1 -Modo integracion backend/modules/academics/tests/test_catalogs_postgresql.py -q
.\scripts\comprobar.ps1 -ConPostgreSQL
.\scripts\django.ps1 migrate --noinput
.\scripts\django.ps1 check --database default --fail-level WARNING
.\scripts\django.ps1 migrate --check
```

Las **63 pruebas nuevas** comprueban columnas, tipos, nulabilidad, CHECK, unicidad, índices funcionales y ordinarios, las seis FK instaladas y sus acciones; valores predeterminados y guardado parcial; homónimos admitidos; dominio único entre instituciones y subdominios distintos; decisiones de dominio completas; SQL inválido, borrado restringido desde SQL y ORM, rollback y relación padre/hijo. Cubren tanto la asignación de un padre incompatible como el cambio de institución de un padre con hijos.

La migración se revierte a cero y reaplica exclusivamente en `test_entrepares`, conservando una cuenta sintética y comprobando las FK restauradas. El flujo general pasó **300 pruebas del servidor —176 sin base y 124 con PostgreSQL— y 68 del cliente**, sin fallos ni omisiones, además de arquitectura, dependencias, Ruff/formato, tipos, build, comprobación de Django, colección y correspondencia de migraciones.

Se aplicó la migración a desarrollo: quince tablas, 18 migraciones y cero filas en las siete tablas de negocio implementadas. La base efímera se eliminó y se mantienen las dos persistentes. La evidencia está en [catalogos-y-ambitos.json](evidencias/catalogos-y-ambitos.json); los registros detallados quedan excluidos de Git en `.cache`.
