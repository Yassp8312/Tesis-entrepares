# Servidor de Entrepares

Esta carpeta reserva la estructura del servidor Django del monolito. Los paquetes Python solo delimitan ubicaciones; todavía no hay una aplicación configurada para arrancar.

Las dependencias se declaran en el `pyproject.toml` de la raíz y se fijan en `uv.lock`. El entorno virtual está en `.venv`, también en la raíz. `scripts/verificar_dependencias.py` comprueba el conjunto instalado con una configuración sintética sin conectar con una base ni ejecutar migraciones.

- `config`: configuración de entornos, rutas y WSGI.
- `api/v1`: solicitudes HTTP, validación de formatos y serialización.
- `application`: casos de uso, permisos vigentes y coordinación transaccional.
- `modules`: diez responsabilidades propietarias de sus registros.
- `core`: reloj, identificadores y tipos técnicos mínimos.

Los modelos, contratos internos, comandos, selectores, pruebas y migraciones se incorporarán en los trabajos correspondientes. El usuario propio de `modules/identity` debe existir antes de aplicar la primera migración de autenticación.
