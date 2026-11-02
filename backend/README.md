# Servidor de Entrepares

Esta carpeta contiene el proyecto Django inicial del monolito. `manage.py` utiliza los ajustes de desarrollo; la entrada WSGI utiliza producción salvo selección explícita del entorno. Los paquetes distintos de identidad siguen reservando ubicaciones para sus incrementos.

Las dependencias se declaran en el `pyproject.toml` de la raíz y se fijan en `uv.lock`. El entorno virtual está en `.venv`, también en la raíz. `scripts/verificar_dependencias.py` comprueba el conjunto instalado con una configuración sintética sin conectar con una base ni ejecutar migraciones.

- `config`: configuración de entornos, rutas y WSGI.
- `api/v1`: solicitudes HTTP, validación de formatos y serialización.
- `application`: casos de uso, permisos vigentes y coordinación transaccional.
- `modules`: diez responsabilidades propietarias de sus registros.
- `core`: reloj, identificadores y tipos técnicos mínimos.

`modules/identity` define `Account` sobre `identity_account`, su gestor y su primera migración. Los contratos internos, comandos y modelos restantes se incorporarán en sus trabajos. La configuración ya selecciona `AUTH_USER_MODEL = identity.Account` antes de aplicar cualquier migración de autenticación. La base se prepara en SP01-T04.
