# DA05 E02: control ejecutable de dependencias

4 de noviembre de 2026, SP01-T10. Se extrae el análisis AST de las pruebas de T05 a `config.architecture` y se utiliza tanto desde pytest como desde `scripts/verificar_arquitectura.py`. Así se evita mantener reglas diferentes para la comprobación independiente y la suite.

Se conserva la separación de propietarios, HTTP, coordinación y utilidades. La excepción para `application` dentro de los propietarios se limita a archivos de comando directamente bajo `management/commands`; los inicializadores de paquetes no son puntos de entrada autorizados. Las entradas API se mantienen fuera de la prohibición de dependencia de `application` aplicable al negocio.

El comprobador devuelve diagnósticos con archivo, línea y regla y falla ante sintaxis inválida. No ejecuta los imports. La equivalencia `backend.<paquete>` se contempla para que un prefijo alternativo no evite las reglas. No se introduce una excepción de acceso a modelos ajenos.

El flujo común se detiene ante un diagnóstico. Una inyección real en la copia independiente demostró ese rechazo; otro ensayo registró y ejecutó un comando Django temporal que llamó a un caso sintético de `application`. Ambos se retiraron sin incorporarse al producto.

La decisión no convierte el análisis de imports en una prueba de todas las escrituras o dependencias dinámicas. Tampoco concede permisos de negocio a un comando. Sus casos de aplicación seguirán aplicando autorización y transacciones conforme al diseño.

Guía: [Comprobaciones](../comprobaciones.md). Evidencia: [automatizacion.json](../evidencias/automatizacion.json). Las fuentes históricas de arquitectura conservan sus huellas.
