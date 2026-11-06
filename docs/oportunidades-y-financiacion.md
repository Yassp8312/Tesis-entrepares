# Oportunidades y financiación: T18–T22

**SP02-T08**, 6 de noviembre de 2026. M05 (`modules.opportunities`) incorpora sus modelos y `OpportunitiesConfig` a Django. La referencia es el diccionario lógico v1 y su SQL, identificados en [Base documental](base-documental.json). Este incremento implementa persistencia e integridad; los casos de publicación, consulta y gestión se incorporan en sus tareas funcionales.

## Estructura física

| Tabla | Modelo | Columnas | Función |
| --- | --- | --- | --- |
| T18 `opportunities_opportunity` | `Opportunity` | 17 | Titular, autor material, descripción, visibilidad, versiones y fechas |
| T19 `opportunities_lifecycle_event` | `LifecycleEvent` | 10 | Historial con revisión, actor, transición y plazos anterior y resultante |
| T20 `opportunities_need` | `Need` | 7 | Necesidad abierta de colaboración, con disciplina opcional |
| T21 `opportunities_funding` | `Funding` | 8 | Monto estimado, moneda, alcance y modalidad declarados |
| T22 `opportunities_contact` | `OpportunityContact` | 8 | Medios externos expresamente destinados a publicación |

Son **cincuenta columnas, veintiséis CHECK, nueve FK, nueve índices no únicos y dos claves únicas adicionales a las PK**. Los modelos abstractos no crean tablas. T21 tiene como PK `opportunity_id`, mediante `OneToOneField`, sin UUID adicional. Las representaciones textuales de las filas muestran solo su identificador.

La migración `opportunities/0001_opportunities_and_funding` depende de la cuenta inicial intercambiable, `academics/0002_personal_verifications_and_researcher_awards` y `organizations/0001_organizations_and_representation`. Mantiene los nombres y **ON DELETE RESTRICT** real de las nueve FK, no diferibles, mediante SQL reversible y `SeparateDatabaseAndState`. El estado ORM termina con `db_constraint=True`; se verifican las restricciones de PostgreSQL además de las relaciones de Django.

## Titularidad y conservación

`ck_t18_01` exige un titular personal o una organización, excluyendo tanto la doble titularidad como su ausencia. `author_id` conserva por separado a la cuenta que creó el contenido; no se exige que sea el titular. Poder almacenar esa combinación no concede autoridad: el caso de aplicación deberá comprobar la identidad y el contexto vigentes.

La oportunidad de una organización no depende por FK de una representación. Revocar a un representante conserva su autoría material y el contenido de la entidad. Las FK impiden borrar accidentalmente cuentas, entidades, disciplinas u oportunidades con referencias. Cerrar, vencer o retirar mediante los campos correspondientes conserva los registros y sus fechas; no se introduce una política de eliminación periódica o un plazo general de retención.

Los textos obligatorios de T18 deben contener caracteres después de `btrim`. `row_version` es positiva y `validity_revision` no negativa. Guardar parcialmente una fila actualiza `updated_at` sin alterar `created_at`. El incremento de versiones y su comprobación concurrente corresponden a los comandos de negocio posteriores; un `save()` ordinario no implementa ese control por sí solo.

## Vigencia e historial

El ciclo almacenado admite `draft`, `active`, `closed` y `expired`; la visibilidad admite `visible`, `hidden` y `removed`. Son dimensiones independientes. Toda oportunidad que no sea borrador técnico exige publicación, vencimiento y revisión positiva; cuando ambas fechas existen, el vencimiento debe ser posterior a la publicación. El borrador técnico permite preparar la persistencia; no añade una función pública de guardar borradores.

Una fila `active` puede tener ya una fecha vencida. La actividad efectiva debe comprobar `expires_at` contra el reloj de la consulta y la visibilidad por separado. No se incorpora un CHECK dependiente de «ahora» ni se prolonga una oportunidad porque el ejecutor de vencimientos se retrase.

T19 distingue publicación, cierre, extensión, vencimiento y reactivación. Exige revisión positiva, estados del catálogo y actor humano salvo en el vencimiento automático, que requiere actor NULL. `uq_t19_key01 (opportunity_id, validity_revision)` impide repetir una revisión, también frente a inserciones simultáneas. Se conservan el plazo anterior, si existía, y el resultante.

El esquema no verifica por sí solo que cada transición sea válida para su estado de origen, ni que la revisión y fecha de T18 coincidan con el último evento. Ese cambio conjunto, el orden de bloqueo, la auditoría y los avisos se ejecutarán en la transacción del caso correspondiente. Los casos deberán tratar el historial como registros de adición, sin ofrecer edición o borrado; la migración no añade un mecanismo de inviolabilidad ante acceso ORM/SQL privilegiado.

Los índices mantienen la selección de vencimientos de filas `active`, el orden `published_at DESC, id`, la expresión `lower(area)` y las búsquedas por titular, autor, actor y disciplina. El índice parcial de vencimiento usa únicamente el estado almacenado, sin filtrar por el reloj actual.

## Necesidades, financiación y contacto

T20 admite varias descripciones de colaboración, con orden no negativo y disciplina opcional. El texto libre permite expresar necesidades que todavía no tengan correspondencia en el catálogo, sin obligar a crear una disciplina para registrarlas.

La existencia de T21 indica financiación declarada; no se duplica un booleano en T18. La PK permite como máximo una fila por oportunidad. Su alta o retirada, y cualquier cambio del conjunto, deberán formar parte de una transacción. El monto es `numeric(18,2)` con CHECK no negativo. No representa un pago realizado ni añade suscripciones o procesamiento de pagos.

La moneda cumple tres letras ASCII mayúsculas en la base. La lista de monedas permitidas y el rechazo de valores numéricos no finitos se validarán en la entrada funcional de **SP09-T06**; el formato SQL y la comparación no sustituyen esas validaciones. Se conservan los alcances `project` y `collaboration`, y las modalidades `one_off`, `monthly` y `other`. Esta última exige un detalle no vacío. Se admite un estimado de cero, conforme al diseño.

T22 conserva un valor público propio para correo, teléfono, WhatsApp o Telegram, con etiqueta opcional y orden no negativo. No tiene FK a `profiles_contact`, ni un indicador de visibilidad privada. Cambiar, ocultar o eliminar un contacto del perfil no cambia el contacto de una oportunidad. `uq_t22_01 (opportunity_id, kind, value)` impide repetirlo en la misma oportunidad; se concreta como restricción UNIQUE con su índice del mismo nombre, conservando columnas y ausencia de predicado del índice único del SQL de referencia.

**Publicar requiere al menos una necesidad y un contacto público**, además del conjunto de campos válidos y, cuando corresponda, financiación completa. Esa regla entre tablas es DL08 y se aplicará al publicar, no mediante un CHECK aislado de una fila. También quedan para los casos funcionales los formatos de medios externos, normalización, autorización y proyecciones de salida.

SP09 implementará publicación personal y exploración pública; SP10, la gestión de organizaciones; SP11, transiciones y avisos. La duración inicial, las condiciones de reactivación y el tratamiento del fin de mes mantienen las concreciones Q03/Q08; esta migración no selecciona valores ni interpreta propuestas pendientes como aprobadas. La regla acordada de extensión y el aviso una semana antes se integrarán junto con esa política, sin activar aquí tareas programadas.

## Comprobaciones

```powershell
.\scripts\probar.ps1 -Modo integracion backend/modules/opportunities/tests -q
.\scripts\comprobar.ps1 -ConPostgreSQL
.\scripts\django.ps1 migrate --noinput
.\scripts\django.ps1 check --database default --fail-level WARNING
.\scripts\django.ps1 migrate --check
```

Las **126 pruebas nuevas con PostgreSQL real** cubren estructura, CHECK, índices, unicidad, referencias, borrado desde SQL/ORM, titularidad separada de autoría, vigencia almacenada, historial, precisión monetaria, modalidades, necesidades abiertas, contactos independientes, valores predeterminados, guardado parcial y rollback del conjunto. Tres pruebas sincronizan parejas de conexiones distintas para comprobar una inserción y un rechazo por duplicado de financiación, contacto y revisión de vigencia.

Se revierte a cero y reaplica la migración exclusivamente en la base efímera, conservando cuenta, organización y disciplina sintéticas y restaurando el grafo. El flujo general pasó **839 pruebas del servidor —225 sin base y 614 con PostgreSQL— y 68 del cliente**, sin fallos ni omisiones, además de arquitectura, dependencias/bloqueos, Ruff/formato, tipos, build, Django check, colección y correspondencia de migraciones. El informe privado está en `.cache/comprobaciones/20261106T065144Z-2d467b15/informe.json`.

Tras aplicar la migración, desarrollo conserva treinta y tres tablas, 24 migraciones y cero filas en las veinticinco tablas de negocio implementadas. Se mantienen las dos bases persistentes y se eliminó la efímera. Los registros privados de comprobación permanecen en `.cache`; la evidencia compacta es [oportunidades-y-financiacion.json](evidencias/oportunidades-y-financiacion.json).

Trazabilidad: **WI05, M05, T18–T22, DL01/DL08/DL09/DL10/DL19, RNF12 y VD18 parcial**. La tarea no incorpora endpoints ni resultados del piloto y mantiene SP02 abierto.
