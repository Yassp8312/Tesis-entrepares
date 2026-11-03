# Configuración Django y cuenta de acceso

SP01-T03, 2 de noviembre de 2026. Se implementan los ajustes del servidor y T01 Cuenta, con migración inicial generada. La preparación y aplicación posterior de SP01-T04 se documentan en [PostgreSQL local](postgresql-local.md); el alcance y las comprobaciones originales de T03 se conservan a continuación.

## Configuración local

Desde PowerShell, en la raíz del repositorio:

```powershell
.\scripts\preparar-configuracion.ps1
.\scripts\django.ps1 check
```

El primer script crea `.env` si no existe y genera una clave con la función de Django. No imprime la clave ni sobrescribe una configuración existente. `.env.example` contiene los nombres de las variables y datos orientativos; no es una configuración de producción utilizable. El segundo script carga `.env` mediante uv y ejecuta los comandos desde la raíz correcta. El script de preparación de dependencias se mantiene separado.

Las credenciales PostgreSQL se completarán al preparar la base del proyecto. En este incremento `check` no abre una conexión; `migrate` y `runserver` necesitan la base del siguiente trabajo. Las rutas del producto se añadirán con sus contratos y actualmente no existe una interfaz pública de Entrepares.

## Entornos

| Módulo de ajustes | Uso |
| --- | --- |
| `config.settings.base` | Componentes comunes, PostgreSQL, sesiones, CSRF y usuario propio |
| `config.settings.development` | Desarrollo local, depuración y cookies compatibles con HTTP local |
| `config.settings.test` | Datos sintéticos de configuración y destino PostgreSQL de pruebas independiente |
| `config.settings.production` | Sin depuración, HTTPS, cookies seguras, hosts y credenciales explícitos |

La producción rechaza una clave ausente, corta o identificada como clave de pruebas, hosts vacíos o comodines y credenciales de base incompletas. No confía en el encabezado de HTTPS de un proxy por omisión; la opción `DJANGO_TRUST_PROXY_SSL_HEADER` solo debe activarse con un proxy que lo sobrescriba. La configuración de despliegue, certificados, conexión a la base y correo real tendrá su ensayo posterior. El correo de desarrollo y pruebas se conserva en memoria para no imprimir mensajes o tokens.

Las mutaciones anónimas de DRF requieren la protección CSRF explícita prevista en SP01-T06. La configuración común de sesiones y middleware no acredita por sí misma esa protección en endpoints que todavía no se han implementado.

## Cuenta y autenticación

El modelo `modules.identity.models.Account` tiene las nueve columnas de T01: UUID, correo, contraseña codificada, tres banderas técnicas y tres fechas. Conserva `ck_t01_01`, `ck_t01_02` y el índice único funcional `uq_t01_01` sobre `lower(email)`.

El gestor valida el correo y conserva su escritura para entrega, eliminando espacios exteriores. La búsqueda usa `lower` en ambos lados, igual que el índice, en lugar de asumir una transformación de mayúsculas en Python. No se añaden columnas de perfil, verificación, representación o moderación a la cuenta.

Las contraseñas utilizan `set_password` y las comprobaciones de Django. La creación con contraseña aplica los validadores configurados y el máximo de 128 caracteres del contrato. La creación ordinaria rechaza banderas de privilegio técnico; la creación de superusuario es una operación separada. Un uso interno sin contraseña genera una contraseña inutilizable; la futura entrada pública de registro mantiene su contraseña obligatoria. Los guardados parciales conservan la actualización de `updated_at`; las futuras escrituras por `QuerySet.update` deberán actualizarla explícitamente.

`EmailBackend` adapta el correo y reutiliza `ModelBackend` para verificar la contraseña y la habilitación técnica. Sus variantes síncrona y asíncrona usan el gestor propio. `is_active` no representa una sanción del producto y las banderas `is_staff` e `is_superuser` no conceden capacidades de M08. Las operaciones HTTP sin permisos explícitos se deniegan por omisión, incluso para un superusuario técnico.

La unicidad por función no es reconocida por el chequeo genérico `auth.W004`. Se silencia solo ese aviso y se incorpora `identity.E001`, que exige el modelo propio, su identificador por correo y la restricción funcional prevista. La supresión se justifica y prueba en [DA04 E01](decisiones/DA04-E01-cuenta-y-configuracion.md).

## Migración y límites de las comprobaciones

La primera migración de identidad crea `identity_account`; el modelo `auth.User` queda sustituido desde el inicio. `PermissionsMixin` añade dos tablas de enlace técnicas de Django, `identity_account_groups` y `identity_account_user_permissions`. Son infraestructura de permisos técnicos y no amplían las 37 tablas del modelo lógico de negocio.

La migración se generó con el autodetector de Django sin conexión, con las traducciones desactivadas como en el comando estándar, y solo se escribió la migración de identidad. Su grafo y la ausencia de diferencias con los modelos se comprobaron sin aplicar SQL. Las pruebas del servidor PostgreSQL deberán demostrar persistencia, rechazo de correos duplicados por mayúsculas y restricciones reales antes de acreditar esas propiedades en la base.

Se ejecutaron 35 pruebas de este incremento, sin habilitar acceso a una base. Las pruebas de creación sustituyen la persistencia y las de autenticación utilizan cuentas sintéticas; los hash y los validadores son los de Django. Las comprobaciones de producción se ejecutan en procesos aislados para evitar reutilizar los ajustes de pruebas. El resultado no equivale a una evaluación de endpoints de producto ni del piloto.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check backend scripts
```
