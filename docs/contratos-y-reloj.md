# Contratos internos y reloj técnico

SP01-T05, cerrado el 3 de noviembre de 2026; pruebas ejecutadas el 2 de noviembre. Concreción de DA01, DA05 y DA12, con utilidades técnicas para DL20. Las interfaces son llamadas Python dentro del monolito. Los contratos de transporte siguen en la especificación OpenAPI y su adaptación corresponde a `api/v1`.

## Interfaces de los propietarios

Los diez módulos tienen tres paquetes explícitos:

| Paquete | Responsabilidad |
| --- | --- |
| `commands` | Escrituras y reglas del propietario; recibe datos explícitos y devuelve el resultado mínimo requerido |
| `selectors` | Lecturas del propietario; entrega datos delimitados para el consumidor autorizado |
| `contracts` | Tipos de intercambio, independientes de HTTP; los resultados compartidos evitan devolver objetos ORM con relaciones o campos adicionales |

`application` consulta los propietarios, reúne los hechos vigentes y coordina autorización, transacción, auditoría y salida persistente según el caso. La entrada HTTP adapta parámetros y resultados. Las entradas CLI en `management/commands` pueden llamar a `application`. La relación de M01–M10 y sus datos está en [Arquitectura](arquitectura.md).

En este incremento M01 tiene dos funciones ejecutables y un tipo inmutable:

| Interfaz | Contrato y efecto |
| --- | --- |
| `identity.commands.create_account(*, email, password)` | Persiste una cuenta ordinaria mediante el gestor existente y devuelve `AccountState`; exige contraseña y mantiene los validadores y el hash de Django |
| `identity.selectors.get_account_state(*, account_id)` | Consulta identidad y habilitación técnica actuales en una lectura; devuelve `AccountState` o `None` |
| `identity.contracts.AccountState` | UUID `account_id` y booleano `is_active`; sin contraseña, correo, permisos técnicos ni datos de perfil |

El comando es una primitiva de T01. El registro completo coordinará perfil, comprobación, auditoría y notificaciones en sus incrementos. El coordinador es responsable de la transacción que abarque esos efectos. El comando no confirma por su cuenta una transacción externa; una excepción en el coordinador revierte su inserción. No acepta banderas de privilegio técnico.

El selector no aplica por sí solo la autorización del caso. Su resultado es interno y `is_active` expresa habilitación técnica, separada de verificación personal, representación, distinción y capacidades de M08. Se vuelve a consultar cuando el caso necesita hechos actuales. Los paquetes de M02–M10 delimitan las interfaces que se implementarán con sus funciones; no contienen implementaciones ficticias ni completan todavía esos módulos.

## Reloj inyectable

`core.clock.Clock` define `now() -> datetime`. `SystemClock` devuelve la hora del sistema en UTC; `FixedClock` devuelve un instante fijo para comprobaciones deterministas. `as_utc` conserva el instante y los microsegundos al convertir un valor consciente de zona. Rechaza un `datetime` sin desplazamiento definido y no interpreta una cadena o una fecha de calendario como un instante.

La composición del servidor elige el reloj y lo pasa explícitamente. Las pruebas pueden sustituirlo por otro objeto con el mismo contrato. No se modifican el reloj global, `django.utils.timezone.now`, los campos automáticos de los modelos ni las funciones de fecha de PostgreSQL. El reloj sirve para las decisiones del caso; las fechas de persistencia conservan los mecanismos ya definidos en T01.

```python
from datetime import UTC, datetime

from core.clock import FixedClock
from core.correlation import OperationContext

context = OperationContext.start(
    clock=FixedClock(datetime(2026, 10, 24, 12, tzinfo=UTC)),
)
checked_at = context.now()
```

Las decisiones temporales deben obtener `context.now()` en el momento en que corresponda decidir, incluido el tramo transaccional protegido si hay autorización o concurrencia. El contexto consulta de nuevo el reloj cada vez; no conserva un instante de autorización capturado al iniciar la solicitud. Un caso puede reutilizar una lectura concreta para sus comprobaciones coherentes, sin reutilizarla como una autorización válida para operaciones posteriores.

La utilidad no decide duración inicial, reactivación ni calendario de fin de mes de las oportunidades. Q03 y Q08 conservan su estado documental; la regla de mes de calendario se resolverá en el propietario y su política. La futura prueba AT09 debe comprobar el vencimiento de oportunidades reales, incluso si el ejecutor periódico llega tarde.

## Identificadores y correlación

`core.identifiers.new_id()` genera un UUID v4. Los identificadores no conceden acceso ni sustituyen credenciales o tokens de comprobación. La validación de su representación HTTP corresponde a la entrada de API.

`core.correlation.OperationContext` es inmutable y transporta `correlation_id` y la referencia al reloj inyectado. `start(clock=...)` genera la correlación en el servidor. El mismo contexto pasa explícitamente entre las llamadas de una operación; una operación independiente crea el suyo. No utiliza una variable global que pueda mezclarse entre solicitudes, ni almacena actor, organización, permisos o datos personales.

La adaptación HTTP de SP01-T06 vinculará ese UUID con `ApiError.request_id`. Los casos que escriban auditoría lo trasladarán a T37 `correlation_id`. No se confía en un identificador aportado por un cliente para crear esta correlación. La persistencia y la proyección de auditoría se implementarán en M10, conforme a DL18.

## Comprobación de límites

Las pruebas AST examinan las importaciones estáticas del código actual de `core` y los propietarios, excluyendo los paquetes de pruebas. Comprueban que:

- `core` usa la biblioteca estándar y sus utilidades propias.
- Los propietarios mantienen separadas la entrada HTTP y la coordinación `application`.
- Solo los puntos de entrada CLI en `management/commands` admiten la dependencia de `application` dentro de los propietarios.
- Un módulo no importa directamente modelos de otro propietario; las lecturas compartidas utilizan sus selectores.
- Los diez módulos conservan sus tres paquetes de interfaz.

Se ensayan también importaciones prohibidas inyectadas, importaciones relativas y alias, y dependencias válidas de modelos propios y entradas CLI. No hay excepciones aprobadas de lectura directa de modelos ajenos en este incremento. Una excepción futura debe identificar la lectura concreta y su motivo antes de incorporarse al control.

Esta es evidencia parcial de AT01: el análisis de importaciones no demuestra todas las escrituras SQL, las dependencias dinámicas o la autorización de un caso. SP01-T10 ampliará la automatización de estructura; las transacciones coordinadas y sus pruebas corresponden a los incrementos funcionales. La prueba de rollback de T01 no acredita la coordinación multímódulo de SP02-T14.

## Reproducir las comprobaciones

```powershell
.\scripts\probar.ps1 -Modo todas -q
.\.venv\Scripts\python.exe -m pytest backend/core/tests backend/tests -q
.\.venv\Scripts\ruff.exe check backend scripts
.\.venv\Scripts\ruff.exe format --check backend scripts
```

La ejecución completa incluye PostgreSQL, datos sintéticos y la base efímera protegida. No cambia el esquema de T01 ni incorpora endpoints o pantallas. Los resultados y las huellas están en [contratos-y-reloj.json](evidencias/contratos-y-reloj.json); la decisión está en [DA05 E01](decisiones/DA05-E01-contratos-y-tiempo.md).

## Referencias

- Base local: registro de arquitectura v1, diccionario lógico v1 y plan SP01-T05, identificados en [Base documental](base-documental.json).
- [Instantes conscientes de zona y UTC en Python 3.13](https://docs.python.org/3.13/library/datetime.html#aware-and-naive-objects).
- [Protocolos y anotaciones de tipos de Python](https://docs.python.org/3.13/library/typing.html#typing.Protocol). Las anotaciones no sustituyen la validación de las entradas ni acreditan por sí mismas un análisis de tipos.
- [Tratamiento de zonas horarias en Django 5.2](https://docs.djangoproject.com/en/5.2/topics/i18n/timezones/).
