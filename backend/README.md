# Servidor de Entrepares

Esta carpeta contiene el proyecto Django inicial del monolito. `manage.py` utiliza los ajustes de desarrollo; la entrada WSGI utiliza producción salvo selección explícita del entorno. Los paquetes distintos de identidad siguen reservando ubicaciones para sus incrementos.

Las dependencias se declaran en el `pyproject.toml` de la raíz y se fijan en `uv.lock`. El entorno virtual está en `.venv`, también en la raíz. `scripts/verificar_dependencias.py` comprueba el conjunto instalado con una configuración sintética sin conectar con una base ni ejecutar migraciones.

- `config`: configuración de entornos, rutas y WSGI.
- `api/v1`: solicitudes HTTP, validación de formatos y serialización.
- `application`: casos de uso, permisos vigentes y coordinación transaccional.
- `modules`: diez responsabilidades propietarias de sus registros.
- `core`: reloj, identificadores y tipos técnicos mínimos.

`modules/identity` define `Account` sobre `identity_account`, su gestor y su primera migración, aplicada en SP01-T04. Sus interfaces `commands` y `selectors` devuelven `contracts.AccountState`, un estado técnico mínimo. Los diez módulos tienen sus paquetes de interfaz; las funciones restantes se incorporarán en sus incrementos. `core` aporta reloj inyectable, UUID y correlación explícita. Consulta [Contratos internos y reloj](../docs/contratos-y-reloj.md).

La base `api.views.JSONAPIView` valida consulta y cuerpo declarados y exige CSRF también sin sesión. `api.middleware` delimita las respuestas JSON y la correlación; `api.errors`, `parsers`, `serializers` y `pagination` preparan los contratos comunes. Consulta [Entrada JSON](../docs/entrada-json.md) antes de registrar una operación de negocio. El URLConf del producto no incorpora las rutas sintéticas de los ensayos.
