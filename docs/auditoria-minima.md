# Auditoría mínima

SP02-T07 incorpora **M10**, propietario de la evidencia transversal, con `AuditEvent` y la migración `audit/0001_audit_events`. La base es T37 del diccionario y SQL de referencia, conservados sin modificaciones. Este incremento prepara la persistencia y una interfaz interna de escritura; cada caso funcional deberá incorporar los eventos que le correspondan.

## Datos e integridad

Se conservan las catorce columnas del diseño:

| Grupo | Columnas | Regla |
| --- | --- | --- |
| Identificación | `id`, `occurred_at`, `correlation_id` | UUID del evento, instante y correlación de operación |
| Actor | `actor_kind`, `actor_account_id` | Una cuenta identificada o un proceso de sistema sin cuenta |
| Contexto | `context_kind`, `organization_id`, `academic_scope_id` | Personal, organizacional o de sistema; ámbito académico opcional |
| Decisión | `action_code`, `resource_kind`, `resource_id`, `reason` | Acción, referencia histórica y motivo cuando corresponda |
| Proyecciones | `before_state`, `after_state` | Objetos mínimos anterior y posterior, o NULL SQL |

Los ocho CHECK comprueban los catálogos de actor y contexto, códigos no vacíos, coherencia entre actor y cuenta, presencia de entidad exclusivamente en contexto organizacional y tipo objeto de las proyecciones JSON. El sistema solo puede actuar en contexto de sistema; una cuenta solo puede actuar en contexto personal u organizacional.

Las tres FK `fk_t37_01`–`fk_t37_03` enlazan cuenta, organización y ámbito, con **ON DELETE RESTRICT** efectivo y no diferible. Se gestionan mediante SQL reversible y `SeparateDatabaseAndState`; las relaciones ORM quedan con `db_constraint=True`. No se añade una FK genérica sobre `resource_id`: la referencia histórica puede conservarse aunque el recurso operativo ya no exista.

Los cinco índices son los previstos: recurso/tipo/instante, actor/instante, correlación, organización y ámbito. La correlación no es única: varios eventos de una operación pueden compartirla sin sobrescribirse. Tampoco se añade una restricción de unicidad sobre el recurso.

`jsonb_typeof` distingue objetos de listas, cadenas, números, booleanos y el valor JSON `null`; se admite **NULL SQL** para una proyección ausente y `{}` para un objeto vacío. La semántica procede de las [funciones JSON de PostgreSQL 17](https://www.postgresql.org/docs/17/functions-json.html); la representación ORM utiliza [JSONField de Django](https://docs.djangoproject.com/en/5.2/ref/models/fields/#django.db.models.JSONField). El CHECK de tipo no examina la privacidad de las claves o valores: esa responsabilidad requiere una proyección explícita al escribir.

## Interfaz propietaria y minimización

`modules.audit.commands.append_event(entry=..., operation=...)` es la interfaz de escritura de M10. Recibe `AuditEntry` y el `OperationContext` técnico del servidor, y devuelve el DTO inmutable `AuditReceipt`, limitado a identificador del evento, correlación e instante. Los llamadores no reciben el modelo ORM.

La entrada inicial es cerrada:

- Actor y contexto usan enumeraciones; las referencias son UUID y deben formar una combinación coherente.
- Acción y tipo de recurso son identificadores técnicos de hasta ochenta caracteres. Deben proceder de constantes del caso de aplicación, nunca del texto suministrado por un usuario. La comprobación de formato no determina por sí sola su significado o la autoridad del actor.
- `AuditProjection` solo permite `status` del catálogo técnico, `related_resource_id` UUID y `revision` entera no negativa. No acepta diccionarios arbitrarios, listas, anidamientos o campos de contacto, contraseña, documento y token. Su exportación crea un objeto nuevo.
- `reason` recibe exclusivamente un valor de `AuditReason`: creación, actualización, aprobación, rechazo, retirada, revocación, caducidad, cierre, reactivación, ampliación o fallo. Se almacena su código técnico; no se admite texto libre en esta primera interfaz.

Esta concreción inicial evita duplicar relatos y documentos privados en el registro transversal. La explicación detallada de una decisión y sus respaldos deben conservarse en el registro privado de su módulo propietario; el recurso o la referencia relacionada permiten localizarlo mediante el acceso autorizado correspondiente. El código técnico no sustituye ese relato cuando el caso lo exige.

Al integrar cada caso se revisará si necesita otros estados, motivos o campos mínimos. Las ampliaciones deberán declararse explícitamente, justificar su necesidad y comprobar su privacidad; no se abrirá un parámetro JSON genérico. La selección inicial no declara implementada la auditoría de todas las operaciones. Se mantienen las catorce columnas T37 y el formato de lectura previsto para API098/API099.

Los DTO son inmutables y la interfaz vuelve a validarlos antes de acceder a la base. Los errores de validación no reproducen el valor rechazado. Esto limita inclusiones accidentales mediante la interfaz soportada; no constituye una protección frente a un llamador interno deliberadamente malicioso o frente a SQL ejecutado con privilegios de propietario.

## Transacciones, tiempo y acceso

`append_event` utiliza el reloj y la correlación de `OperationContext`; no recibe una fecha ni correlación independientes desde un cuerpo HTTP. El instante se normaliza a UTC mediante el contrato técnico existente. Los valores predeterminados de UUID y tiempo de PostgreSQL se conservan para la integridad del esquema.

La escritura participa en la transacción del llamador. No confirma una transacción propia ni produce efectos externos. `application` deberá comprobar autoridad vigente, construir la evidencia y coordinar cambio de negocio, evento obligatorio y salida persistente en su transacción. La prueba de rollback de T07 comprueba esa participación con datos sintéticos; **SP02-T14** implementará la coordinación prevista, incluidos sus fallos y bloqueos.

La interfaz soportada solo añade eventos: no ofrece comandos de modificación ni borrado. La base no incorpora un mecanismo de inviolabilidad frente a su administrador y el acceso directo ORM/SQL conserva los privilegios de su rol. Esta es la condición «append-only por aplicación» del diseño.

No se crean endpoints o permisos efectivos al instalar M10. La consulta API098/API099 seguirá requiriendo `audit.read`, filtro por ámbito y tipos de decisión permitidos, también al abrir un evento por identificador. Esa lectura corresponde a **SP14-T04**. Representar una organización o ser superusuario técnico no habilita su consulta por esta migración.

## Comprobar y aplicar

```powershell
.\scripts\probar.ps1 -Modo todas backend/modules/audit/tests -q
.\scripts\comprobar.ps1 -ConPostgreSQL
.\scripts\django.ps1 migrate --noinput
.\scripts\django.ps1 check --database default --fail-level WARNING
.\scripts\django.ps1 migrate --check
```

Las 95 pruebas nuevas se distribuyen en **49 sin base** y **46 sobre PostgreSQL real**. Comprueban entradas y proyecciones cerradas, errores sin contenido privado, referencias, coherencia de actor/contexto, esquema, índices, valores predeterminados, JSON NULL frente a NULL SQL, borrado restringido desde SQL y ORM, escritura mínima, correlación compartida, reloj inyectado y rollback conjunto. La migración se revierte y reaplica exclusivamente en la base efímera, conservando registros sintéticos previos y restaurando el grafo.

El flujo general pasó **713 pruebas del servidor —225 sin base y 488 con PostgreSQL— y 68 del cliente**, sin fallos ni omisiones. También pasaron arquitectura, dependencias/bloqueos, Ruff/formato, tipos, build, Django check, colección y correspondencia de migraciones. El informe privado está en `.cache/comprobaciones/20261106T063713Z-92281430/informe.json`.

Tras aplicar la migración, desarrollo conserva veintiocho tablas, 23 migraciones y cero filas en las veinte tablas de negocio implementadas. Se conservan las dos bases persistentes y la base efímera se eliminó. La evidencia compacta se registra en [auditoria-minima.json](evidencias/auditoria-minima.json). La trazabilidad es **WI05, M10, T37, DL18, RNF12 y aportes parciales a AT18/VD18**. Los registros privados permanecen en `.cache`; estas pruebas no son resultados del piloto ni cierran SP02.
