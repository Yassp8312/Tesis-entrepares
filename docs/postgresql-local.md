# PostgreSQL local de desarrollo y pruebas

SP01-T04. Distribución Windows x64 de PostgreSQL 17.11, independiente de los servicios de Windows. Los binarios, datos, registros y credenciales permanecen en `.tools/postgresql/17.11`, excluido de Git. Escucha únicamente en `127.0.0.1`, por omisión en el puerto 55432.

## Preparación

Con las dependencias y la configuración local ya preparadas, ejecutar desde la raíz del repositorio:

```powershell
.\.venv\Scripts\python.exe scripts\postgresql_local.py preparar
.\scripts\django.ps1 migrate --noinput
.\scripts\django.ps1 check --database default --fail-level WARNING
```

La primera ejecución descarga el archivo del distribuidor, comprueba tamaño, SHA256 fijada y CRC del ZIP, extrae el runtime e inicializa un cluster UTF-8 con proveedor de ordenación ICU y locale `und`. La descarga usa partes reutilizables para poder reanudarla. `scripts/postgresql-runtime.json` identifica el archivo exacto y su procedencia. Su SHA256 se calculó sobre la descarga inicial por HTTPS, comprobada por tamaño y CRC; no se presenta como una firma ni como una suma publicada por el distribuidor.

`preparar` genera contraseñas aleatorias, configura SCRAM-SHA-256, crea los roles y las bases y completa las variables PostgreSQL de `.env`. Conserva la clave Django, las credenciales del cluster y los datos al repetirlo. No reinicializa un directorio de datos existente ni cambia el propietario de una base ajena. Rechaza sobrescribir credenciales o destinos externos reconocidos en `.env`. Si el puerto está ocupado, se detiene sin intervenir ese proceso; para un cluster aún no creado se puede elegir otro con `preparar --port 55433`.

No crea un servicio de Windows ni modifica el PATH. Se usa el runtime privado, aunque exista otra instalación de PostgreSQL. No necesita Docker, una cuenta de servicio ni una suscripción. Es una preparación para desarrollo local; el despliegue del piloto tendrá su configuración y comprobaciones propias.

## Bases y privilegios

| Destino | Rol | Uso y alcance |
| --- | --- | --- |
| `entrepares_development` | `entrepares_dev` | Propietario para desarrollo y migraciones; sin superusuario, creación de bases, roles, replicación ni evasión de RLS |
| `entrepares_test` | `entrepares_test` | Base de conexión para pruebas; sin superusuario ni administración de roles; puede crear bases para pytest-django |
| `test_entrepares` | `entrepares_test` | Base efímera que Django crea, migra y destruye en cada ejecución de integración |
| Cluster privado | `entrepares_bootstrap` | Administrador de aprovisionamiento; su contraseña queda fuera de `.env` y no se usa desde Django |

Las dos bases persistentes revocan el acceso de `PUBLIC`. El rol de pruebas puede conectar a `postgres` para la creación de la base efímera; el rol de desarrollo no puede hacerlo. La base efímera revoca también el acceso de `PUBLIC` antes de ejecutar las pruebas. Los roles de aplicación no tienen acceso cruzado entre desarrollo y pruebas. El permiso `CREATEDB` del rol de pruebas se limita a este cluster de uso local; no se propone para el usuario de producción.

La configuración externa incluye host, puerto, base, usuario y contraseña separados para pruebas y desarrollo. `POSTGRES_TEST_CLUSTER_NAME` identifica mediante una etiqueta aleatoria el cluster que el aprovisionamiento preparó. `.env.example` documenta las variables sin contraseñas operativas. No copiar `.env`, `secrets.json` ni el directorio de datos al repositorio o a documentos públicos.

## Arranque y parada

```powershell
.\.venv\Scripts\python.exe scripts\postgresql_local.py estado
.\.venv\Scripts\python.exe scripts\postgresql_local.py iniciar
.\.venv\Scripts\python.exe scripts\postgresql_local.py detener
```

Los comandos verifican el directorio de datos, la versión y la etiqueta del servidor conectado. `detener` usa una parada controlada del cluster propio; no borra datos. Tras reiniciar Windows, ejecutar `iniciar` antes de utilizar Django. Los detalles de fallos nativos están en el archivo privado `.tools/postgresql/17.11/operaciones.log`; el registro del servidor está en `servidor.log` del mismo directorio.

## Pruebas

```powershell
.\scripts\probar.ps1 -Modo unitarias -q
.\scripts\probar.ps1 -Modo integracion -q
.\scripts\probar.ps1 -Modo todas -q
```

El script arranca el cluster cuando se necesita, carga `.env` y fuerza `config.settings.test`, aunque ese archivo declare el entorno de desarrollo. La invocación directa `python -m pytest` selecciona las pruebas sin base por omisión; para incluir PostgreSQL utilizar el script.

Antes de crear o destruir una base, las fixtures exigen el módulo de pruebas, host local, nombres de base y rol previstos, contraseña y coincidencia de la etiqueta del cluster y de la serie 17. Un destino diferente produce un error y no inicia la preparación de la base de pruebas. No usar `--reuse-db` o `--create-db` para sortear un error de identificación.

Las pruebas de integración usan datos sintéticos y comprueban el esquema real de T01, la ausencia de `auth_user`, persistencia y hash de contraseña, identificación por correo, rechazo de duplicados por mayúsculas, CHECK ejecutados mediante SQL, valores predeterminados de base, actualización de fecha, autenticación, recuperación de sesión con UUID y aislamiento por permisos. No acreditan aún endpoints de registro, capacidades M08, concurrencia del producto, copias de seguridad, rendimiento ni resultados del piloto.

La evidencia del incremento está en [postgresql-local.json](evidencias/postgresql-local.json). Las 37 tablas de negocio se implementarán según sus incrementos: este paso aplica las migraciones Django disponibles, sin ejecutar sobre ellas el SQL completo de referencia del diseño.

## Referencias técnicas

- [Distribución de binarios de EDB](https://www.enterprisedb.com/download-postgresql-binaries).
- [Inicialización y selección de locale de PostgreSQL 17](https://www.postgresql.org/docs/17/app-initdb.html).
- [Control del servidor con pg_ctl](https://www.postgresql.org/docs/17/app-pg-ctl.html).
- [Privilegios de roles de PostgreSQL 17](https://www.postgresql.org/docs/17/role-attributes.html).
- [Fixtures de preparación de base de pytest-django](https://pytest-django.readthedocs.io/en/latest/database.html#django-db-modify-db-settings).
