# Seguimiento de implementación

## 30 de octubre de 2026

SP01-T01 prepara el repositorio y sus ubicaciones iniciales: cliente, servidor, documentación, configuración y diez módulos internos con responsabilidad identificada. Se incorporan exclusiones de secretos y datos locales, convenciones de formato y reglas de arquitectura.

Se comprobó la correspondencia de los diez módulos con el registro de arquitectura, la sintaxis de los paquetes Python y la identificación de siete fuentes mediante SHA256. Git excluyó las 18 rutas representativas de archivos privados o generados examinadas y conservó las diez rutas de código, migraciones, ejemplos y dependencias examinadas. La rama inicial es `main`, sin remotos configurados. Estas comprobaciones de preparación se registran en `evidencias/repositorio-inicial.json`; los escenarios AT01 y AT18 del producto todavía no se han ejecutado sobre una aplicación.

Los estados de los documentos de planificación conservan su versión de diseño. Este registro identifica el avance de implementación posterior; cerrar SP01-T01 no termina WI06 ni el sprint SP01.

## Siguiente trabajo

SP01-T02 se completó con Python 3.13.17, Django 5.2.18, DRF 3.18.3, Node 24.18.0 y las dependencias Vue fijadas. `uv.lock` y `frontend/package-lock.json` permiten reproducir las versiones. Se preparó el script Windows `scripts/preparar-entorno.ps1`, con descarga de uv verificada por SHA256, Python local sin registro global, instalación bloqueada y comprobaciones técnicas.

Se ejecutó el script completo y se repitió la instalación en una carpeta independiente con un entorno virtual y un `node_modules` nuevos. Coincidieron los 16 paquetes Python instalados y las huellas de ambos bloqueos; funcionaron los imports, los ajustes sintéticos de Django, el adaptador PostgreSQL, el análisis Ruff, los tipos Vue/TypeScript, una compilación Vite y una ruta en memoria. No se abrió una conexión a la base ni se aplicaron migraciones.

La referencia DRF 3.16 se ajustó mediante [DA03 E01](decisiones/DA03-E01-dependencias.md): la auditoría inicial encontró siete registros equivalentes a cinco avisos; el corte final con 3.18.3 no presentó avisos en uv ni npm. Estas consultas no certifican la seguridad del producto. La evidencia compacta está en `evidencias/dependencias.json`; los originales de QA permanecen fuera de los archivos versionados del producto.

## 2 de noviembre de 2026

SP01-T03 incorpora `manage.py`, ajustes separados de desarrollo, prueba y producción, WSGI, configuración local excluida de Git y el modelo `identity.Account` con su primera migración. Mantiene las nueve columnas T01, los dos CHECK y la unicidad funcional del correo. La autenticación reutiliza Django y las operaciones HTTP sin permisos explícitos se deniegan por omisión.

Pasaron 35 pruebas sin acceso a una base, Ruff y los chequeos de Django. La migración coincide con los modelos y sustituye `auth.User` en su grafo. Las pruebas incluyen contraseñas reales codificadas, reglas de creación, búsqueda y autenticación sintéticas, rechazo de configuraciones de producción incompletas y denegación de una vista no configurada a un superusuario técnico. La evidencia está en `evidencias/configuracion-y-cuenta.json` y la decisión técnica en [DA04 E01](decisiones/DA04-E01-cuenta-y-configuracion.md). El aviso genérico `auth.W004` se sustituye por un control específico del índice funcional; la salida de `check` refleja un aviso silenciado.

El siguiente trabajo es **SP01-T04**, preparar PostgreSQL de desarrollo y prueba y aplicar las migraciones sobre una base vacía. Se deben comprobar allí los duplicados por mayúsculas y las restricciones reales. El servicio existente y sus datos no se han intervenido; no se abrió una conexión ni se aplicó SQL en T03. SP01-T05 prepara contratos y reloj técnicos; SP01-T07 puede preparar Vue. El sprint SP01 y WI06 siguen abiertos.
