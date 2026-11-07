# FK compuestas y vistas derivadas

**SP02-T12**, 7 de noviembre de 2026. Se consolidan las siete FK compuestas instaladas en sus tareas propietarias y se incorporan las cuatro vistas del SQL lógico de referencia. Las fuentes históricas permanecen intactas; su identificación está en [Base documental](base-documental.json).

## Relaciones conservadas

| Restricción | Columnas de origen → referencia | Garantía estructural |
| --- | --- | --- |
| `fk_t09_02` | ámbito `(parent_id, institution_id)` → ámbito `(id, institution_id)` | Padre de la misma institución |
| `fk_t12_02` | respaldo `(challenge_id, account_id)` → comprobación `(id, account_id)` | Comprobación de la misma cuenta |
| `fk_t14_05` | distinción `(source_request_id, account_id, academic_scope_id)` → solicitud `(id, account_id, academic_scope_id)` | Solicitud de la misma persona y ámbito |
| `fk_t24_01` | detalle `(publication_id, publication_kind)` → publicación `(id, kind)` | El detalle corresponde al tipo evento |
| `fk_t30_01` | revisión `(measure_id, requested_by)` → medida `(id, account_id)` | Revisión de la propia persona afectada |
| `fk_t33_07` | concesión `(parent_grant_id, granted_by)` → concesión `(id, account_id)` | La fuente pertenece al otorgante |
| `fk_t34_01` | aviso `(opportunity_id, validity_revision)` → evento `(opportunity_id, validity_revision)` | Aviso ligado a una revisión histórica existente |

Las siete restricciones ya se crearon mediante SQL reversible junto con sus modelos. Esta tarea **las conserva sin eliminarlas, duplicarlas o sustituirlas por FK simples**. Se comprueban las 22 FK de sus siete tablas, con nombres, columnas y orden, referencias, `ON DELETE RESTRICT`, validación y carácter no diferible; también que no aparezca otra FK compuesta ajena al diseño.

Se verifica que los ocho campos ORM asociados a relaciones gestionadas por SQL mantienen `db_constraint=False`, tanto en los modelos instalados como en el estado histórico de migraciones. Son `AcademicScope.parent`, `PersonalVerification.challenge`, `ResearcherAward.source_request`, `EventDetail.publication`, `ReviewRequest.measure`, `ReviewRequest.requested_by`, `Grant.parent_grant` y `Notice.opportunity`. Las FK simples complementarias mantienen sus definiciones. La comparación general entre modelos y migraciones debe seguir sin diferencias.

Estas relaciones conservan correspondencia de datos. La autoridad del actor, vigencia, ausencia de ciclos, transición válida o legitimidad de una decisión siguen las reglas del caso; una FK no las demuestra por sí sola.

## Vistas y propiedad

| Vista SQL | Propietario y migración | Columnas |
| --- | --- | --- |
| `model_profile_completeness` | M02, `profiles/0002_profile_completeness_view` | `profile_id`, `account_id`, `is_complete` |
| `model_personal_verification` | M03, `academics/0003_personal_verification_view` | `account_id`, `is_verified` |
| `model_organization_verification` | M04, `organizations/0002_organization_verification_view` | `organization_id`, `is_verified` |
| `model_opportunity_funding` | M05, `opportunities/0002_opportunity_funding_view` | `opportunity_id`, `is_funded` |

Cada propietario crea su vista con `RunSQL` y la retira con `DROP VIEW`, sin `CASCADE`. Las dependencias apuntan a la migración de sus tablas de origen, de modo que la reversión elimina la vista antes de retirar esas tablas. Las definiciones reproducen las cuatro consultas de referencia.

Son vistas SQL ordinarias, no materializadas. Consultan los registros visibles en la transacción actual sin duplicar indicadores editables ni requerir un proceso de refresco. No se crean tablas nuevas, modelos de escritura para las vistas o columnas de estado en las tablas existentes. El estado ORM conserva los modelos de origen; las vistas se administran explícitamente mediante sus migraciones SQL.

La completitud exige formación vigente y al menos un contacto visible. El nombre no vacío y los campos obligatorios de formación ya están garantizados por los CHECK, NOT NULL y FK de origen; por eso la consulta de referencia usa dos `EXISTS`. Varias formaciones o contactos no multiplican la fila del perfil. Un perfil completo puede pertenecer a una cuenta sin verificar: la verificación determina las condiciones del lector, no este hecho de completitud.

La verificación personal equivale a la existencia de al menos un respaldo `approved`. No se escoge simplemente el último expediente. Una solicitud pendiente, un rechazo o una retirada no anulan otro respaldo todavía aprobado. Cambiar formación, correo o estado del dominio no altera automáticamente ese respaldo. La nueva afiliación continúa declarada; el booleano de cuenta no acredita cada formación. La habilitación técnica `is_active` se evalúa por separado.

La verificación de organización se deriva de sus expedientes aprobados y permanece separada de la verificación personal o la vigencia de una representación. Revocar a un representante no retira por sí mismo el respaldo de la entidad. La financiación se deriva de la presencia de T21, incluido un estimado de cero; no se confunde con actividad o visibilidad de la oportunidad.

## Lecturas propietarias

Los módulos exponen `get_profile_completeness`, `get_personal_verification`, `get_organization_verification` y `get_opportunity_funding` en sus paquetes `selectors`. Cada función consulta su vista mediante SQL fijo y parámetro enlazado, con una sola lectura por identificador. Devuelve un DTO inmutable con las columnas indicadas, o `None` si el recurso no existe. Un recurso existente con resultado falso se distingue de un identificador ausente.

Los contratos son `ProfileCompletenessState`, `PersonalVerificationState`, `OrganizationVerificationState` y `OpportunityFundingState`. No devuelven modelos ORM, contactos, nombres, correos, motivos, pruebas documentales, importes ni contenido de proyectos. Las lecturas no importan modelos de propietarios ajenos. La lectura M03 sobre identidad y respaldos queda delimitada en la definición de su vista.

Estos selectores son interfaces internas de hechos. `application` deberá comprobar autorización y construir la proyección del caso antes de entregar una respuesta. No son endpoints ni un permiso de acceso por conocer el UUID. Las vistas tampoco implantan RLS, permisos de columna o una garantía de solo lectura frente al rol propietario de la base. La consulta de una vista no sustituye los bloqueos y la revalidación necesarios ante cambios concurrentes de autorización.

## Comprobaciones y límites

```powershell
.\scripts\probar.ps1 -Modo integracion backend/application/tests/test_derived_views_postgresql.py -q
.\scripts\comprobar.ps1 -ConPostgreSQL
.\scripts\django.ps1 migrate --noinput
.\scripts\django.ps1 check --database default --fail-level WARNING
.\scripts\django.ps1 migrate --check
```

Las **41 pruebas nuevas de PostgreSQL** cubren las siete relaciones compuestas y sus FK complementarias, estado ORM histórico, estructura exacta de vistas, combinaciones de formación/contacto, cambios de respaldo, separación entre persona y entidad, financiación y ausencia de caché de indicadores. Se comprueban DTO mínimos inmutables, una consulta por selector, identificadores ausentes y rollback de hechos derivados.

Cuatro ensayos revierten y reaplican cada migración de vista, sin retirar las otras tres, perder datos de origen o cambiar las relaciones compuestas. La suite general incluye además los rechazos de tuplas incompatibles de las tareas anteriores. Las comprobaciones se ejecutan sobre una base efímera y datos sintéticos; una restauración desde copia física y el piloto mantienen sus tareas específicas.

El flujo general pasó **1173 pruebas del servidor —225 sin base y 948 con PostgreSQL— y 68 del cliente**, sin fallos ni omisiones, además de arquitectura, dependencias/bloqueos, Ruff/formato, tipos, build, Django check, colección y correspondencia de migraciones. Informe privado `.cache/comprobaciones/20261107T052820Z-d9046cc3/informe.json`.

Tras aplicar las cuatro migraciones, desarrollo conserva 45 tablas, 31 migraciones, las cuatro vistas y cero filas en las 37 tablas de negocio. Las siete FK compuestas mantienen sus mismas definiciones. Se conservan las dos bases persistentes y se eliminó la efímera. La evidencia compacta es [fk-compuestas-y-vistas.json](evidencias/fk-compuestas-y-vistas.json).

Trazabilidad: **WI05, M01–M10, DL01–DL20, RNF12, VD18 y aporte parcial a AT15**. Esta tarea no cierra SP02 ni completa las políticas o los casos funcionales.
