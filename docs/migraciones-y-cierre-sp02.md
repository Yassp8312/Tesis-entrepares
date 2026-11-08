# Migraciones y cierre técnico de SP02

**SP02-T17 · 8 de noviembre de 2026 · WI05 / RNF12.** Esta entrega cierra las 17 tareas del sprint «Modelo físico y soportes transversales». La evidencia de instalación, segunda aplicación y reversión se registra en [migraciones-y-cierre-sp02.json](evidencias/migraciones-y-cierre-sp02.json). Las fuentes de diseño conservan sus huellas y estados históricos.

## Instalación y reproducción

Para instalar o actualizar el entorno de desarrollo ya preparado se usa el comando habitual, después de revisar su configuración local:

```powershell
.\scripts\django.ps1 migrate --plan
.\scripts\django.ps1 migrate --noinput
.\scripts\django.ps1 makemigrations --check --dry-run
.\scripts\django.ps1 migrate --check
```

La reproducción destructiva tiene un punto de entrada diferente:

```powershell
.\scripts\comprobar_migraciones.ps1 -Salida .cache/migraciones/informe.json
```

Este segundo comando carga el entorno fijado y fuerza los ajustes de prueba solo en su proceso. Exige host local, rol y base de preparación `entrepares_test`, destino `test_entrepares`, contraseña de prueba y el nombre exacto del cluster privado PostgreSQL 17. Comprueba servidor, usuario y base por conexión real. **Si `test_entrepares` ya existe, rechaza continuar y no la modifica ni elimina**. No debe ejecutarse al mismo tiempo que otra suite de integración.

Crea la base desde `template0`, retira los privilegios de PUBLIC y comprueba que no contiene tablas ni vistas. Aplica las migraciones mediante Django, contrasta el esquema con la referencia versionada de T16 y exige cero filas de negocio. Inserta únicamente un grafo sintético de una fila por tabla. La segunda aplicación debe tener plan vacío y conservar catálogo, las 37 filas y el historial de migraciones con sus fechas. Las huellas publicadas corresponden a esa ejecución; las del corpus cambian entre ejecuciones por sus UUID y contraseñas inutilizables.

Después revierte todo el grafo en esa misma base efímera, comprueba que solo queda `django_migrations` vacío y vuelve a instalar y contrastar el esquema. Finalmente cierra su conexión y elimina exclusivamente la base que creó, comprobando previamente OID y propietario. No usa `DROP DATABASE ... FORCE`, no termina sesiones ajenas ni borra directorios. Un fallo también intenta esta limpieza; si otra conexión impide eliminar la base, se informa del fallo y la siguiente ejecución la rechazará. El informe de éxito se escribe después de completar la limpieza.

## Orden y dependencias

Hay **31 migraciones: 16 del producto y 15 de Django**. El orden válido lo determina el grafo de Django, no una lista manual de comandos por módulo. La evidencia incluye los 31 nodos, sus dependencias declaradas y el orden observado. Dos ramas independientes pueden cambiar de posición sin alterar las dependencias.

En esta instalación, `contenttypes/0001` y `0002` precedieron a `auth/0001`–`0012`. `identity/0001_initial` depende de `auth/0012`; crea el usuario propio configurado desde el inicio mediante `AUTH_USER_MODEL=identity.Account`. No se crea una tabla `auth_user`. Las referencias intercambiables `identity/__first__` se resuelven hacia esa primera migración. Las migraciones del framework anteriores no sustituyen al usuario propio.

| Posición observada | Migración del producto | Dependencias directas del producto |
| --- | --- | --- |
| 15 | `identity/0001_initial` | Ninguna; requiere `auth/0012` |
| 16 | `identity/0002_email_challenge_and_recovery_request` | `identity/0001` |
| 17 | `academics/0001_catalogs_and_scopes` | `identity/0001` |
| 18 | `academics/0002_personal_verifications_and_researcher_awards` | `academics/0001`, `identity/0002` y usuario propio |
| 19 | `academics/0003_personal_verification_view` | `academics/0002` |
| 20 | `organizations/0001_organizations_and_representation` | `academics/0001`, usuario propio |
| 21 | `access/0001_capabilities_and_grants` | `academics/0002`, `organizations/0001`, usuario propio |
| 22 | `audit/0001_audit_events` | `academics/0002`, `organizations/0001`, usuario propio |
| 23 | `opportunities/0001_opportunities_and_funding` | `academics/0002`, `organizations/0001`, usuario propio |
| 24 | `publications/0001_publications_events_and_highlights` | `access/0001`, `opportunities/0001`, `organizations/0001`, usuario propio |
| 25 | `moderation/0001_moderation_and_review` | `access/0001`, `opportunities/0001`, `publications/0001`, usuario propio |
| 26 | `notifications/0001_notices_outbox_and_attempts` | `identity/0002`, `opportunities/0001`, usuario propio |
| 27 | `opportunities/0002_opportunity_funding_view` | `opportunities/0001` |
| 28 | `organizations/0002_organization_verification_view` | `organizations/0001` |
| 29 | `profiles/0001_profiles_and_education` | `academics/0001`, usuario propio |
| 30 | `profiles/0002_profile_completeness_view` | `profiles/0001` |

`sessions/0001_initial`, sin dependencias declaradas, ocupó la posición 31. Las dependencias entre esquemas garantizan que existan las tablas referenciadas; no autorizan a un módulo a escribir datos de otro propietario. Las escrituras de casos compartidos conservan la coordinación de `application`.

## Tablas del producto e infraestructura

| Propietario | Tablas lógicas | Tablas físicas |
| --- | --- | --- |
| M01 Identidad | T01–T03 | `identity_account`, `identity_email_challenge`, `identity_recovery_request` |
| M02 Perfiles | T04–T07 | `profiles_profile`, `profiles_education`, `profiles_contact`, `profiles_merit` |
| M03 Gobierno académico | T08–T14 | `academics_institution`, `academics_scope`, `academics_discipline`, `academics_domain`, `academics_personal_verification`, `academics_researcher_request`, `academics_researcher_award` |
| M04 Organizaciones | T15–T17 | `organizations_organization`, `organizations_verification`, `organizations_representation` |
| M05 Oportunidades | T18–T22 | `opportunities_opportunity`, `opportunities_lifecycle_event`, `opportunities_need`, `opportunities_funding`, `opportunities_contact` |
| M06 Divulgación | T23–T25 | `publications_publication`, `publications_event_detail`, `publications_highlight` |
| M07 Moderación | T26–T31 | `moderation_report`, `moderation_decision`, `moderation_measure`, `moderation_restriction`, `moderation_review_request`, `moderation_review_decision` |
| M08 Acceso | T32–T33 | `access_capability`, `access_grant` |
| M09 Notificaciones | T34–T36 | `notifications_notice`, `notifications_outbox`, `notifications_delivery_attempt` |
| M10 Auditoría | T37 | `audit_event` |

Las otras ocho tablas son `django_migrations`, `django_content_type`, `django_session`, `auth_group`, `auth_permission`, `auth_group_permissions`, `identity_account_groups` e `identity_account_user_permissions`. Las dos últimas son relaciones técnicas heredadas de autenticación, aunque compartan prefijo con identidad. No son T38/T39 ni concesiones M08. Los permisos y grupos del framework, `is_staff` o `is_superuser` no conceden autoridad funcional por sí mismos.

`post_migrate` puede crear tipos de contenido y permisos técnicos de Django. **Ninguna migración siembra universidades, dominios reconocidos, capacidades, concesiones, verificaciones o cuentas reales.** Los catálogos operativos y su aprobación se incorporarán por sus procesos autorizados. Las fábricas no son una carga inicial del producto. La disponibilidad de las tablas de catálogo satisface la preparación estructural, sin inventar un listado institucional aprobado.

## Restricciones implementadas y reversibilidad

La instalación contiene **37 tablas de negocio, 345 campos, 37 PK, 85 FK —siete compuestas—, 143 CHECK, 19 restricciones UNIQUE, 153 índices y cuatro vistas ordinarias**. Los ocho objetos tabulares de infraestructura elevan el total a 45. El [contraste de T16](esquema-y-datos-sinteticos.md) especifica los atributos comprobados, las tres representaciones mediante UNIQUE y el índice auxiliar Django; se conservan esos cuatro ajustes técnicos explícitos.

Las FK del producto están validadas, son no diferibles y usan `ON DELETE RESTRICT`. Las siete relaciones compuestas se administran mediante SQL reversible y el estado ORM evita crear FK simples sustitutas en sus ocho campos afectados. Su inventario, columnas y finalidad están en [FK compuestas y vistas](fk-compuestas-y-vistas.md). Las vistas pertenecen a sus módulos y se retiran antes de sus tablas fuente conforme al grafo. No son tablas editables, cachés de permisos o una política RLS.

Los CHECK y los filtros parciales se contrastan en 8568 combinaciones sintéticas con la semántica de NULL correspondiente. Las pruebas de integridad de T01–T16 comprueban relaciones incompatibles, duplicados y rollback; los tipos y las FK no prueban por sí solos autorización, vigencia, ausencia de ciclos o validez institucional. Las transacciones y reglas de aplicación siguen siendo necesarias.

Las operaciones del grafo declaran reversibilidad y el ensayo global la ejecutó con el corpus sintético. **Revertir una migración que elimina tablas elimina sus datos**; reaplicar recupera la estructura, no esos registros. Esta evidencia no es una restauración desde backup, ni demuestra que una futura modificación de columnas sea compatible con datos desplegados. Los procedimientos de copia/restauración, conservación, despliegue y reversión operativa requieren sus ensayos específicos. No se recomienda ejecutar una reversión total sobre desarrollo o producción.

## Criterio de cierre y alcance pendiente

El criterio original de WI05 dice: «Una base vacía se crea mediante migraciones; relaciones, unicidad y datos sintéticos se comprueban sin afirmar que el modelo conceptual sea el esquema final». Se consultó `Lista de trabajo OpenUP.json`, identificada por su huella en la evidencia. Su dependencia WI04 figura terminada como resultado documental de arquitectura, con escenarios técnicos asignados a los incrementos.

| Elemento del criterio | Evidencia que lo satisface |
| --- | --- |
| Base vacía creada por migraciones | Cero tablas/vistas al comenzar, 31 migraciones aplicadas y contraste conforme |
| Relaciones y unicidad | Pruebas PostgreSQL de las tareas propietarias y T16; catálogo de 85 FK, PK, UNIQUE e índices |
| Datos sintéticos | Grafo T01–T37, guardas de destino y preservación íntegra en la segunda aplicación |
| Distinción entre diseño e implementación | Diccionario/SQL originales intactos; ajustes físicos explícitos y contrato estructural versionado |
| Cierre adicional de T17 | Plan vacío en la segunda aplicación, catálogo/datos/historial iguales y reversión/reaplicación comprobadas |

Con ello **WI05 y SP02 quedan cerrados en el registro de implementación**. No se reescribe el estado histórico del plan original. WI08/WI09 y los requisitos transversales mantienen los trabajos que correspondan a los incrementos funcionales; no se declaran globalmente terminados por cerrar este sprint.

El siguiente sprint es **SP03: cuenta, sesión y recuperación**. Implementará los flujos reales de identidad y sus contratos HTTP. Los ejemplos transaccionales y el ejecutor de salida de SP02 son soporte técnico: todavía no hay plantillas funcionales habilitadas, envío SMTP real acreditado, alta/confirmación/recuperación completas ni permisos públicos nuevos. Tampoco se acreditan resultados del piloto o se resuelven automáticamente las condiciones PB/Q y RF45/RF59.
