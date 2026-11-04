# Interfaz de Entrepares

Cliente Vue 3 con TypeScript, Vue Router y cliente HTTP común. `src/api` contiene el transporte, errores y ciclo CSRF; `src/features` aloja las pantallas por funcionalidad. Las dependencias se conservan fijadas en `package.json` y `package-lock.json`.

Con Node y npm en las versiones fijadas, usar `npm ci` para instalar y `npm run dev` para iniciar en `http://127.0.0.1:5173/`; Django debe ejecutarse en `127.0.0.1:8000` para el proxy. `npm run typecheck`, `npm test` y `npm run build` comprueban tipos, transporte y compilación. `npm run check:deps` conserva su muestra técnica independiente en `.cache`.

Hay una portada de presentación, `/acerca-de` y una vista de página no encontrada, con recursos locales de la propuesta de marca y «Apoyar a Jorge» en el pie. Las funciones de negocio todavía se implementarán en sus incrementos. Las licencias distribuidas están en `public/licenses` y la procedencia en la evidencia de la raíz. Consulta [Cliente Vue](../docs/cliente-vue.md) para el origen común, CSRF, límites de la integración y comandos completos.

`src/components` contiene botones, enlaces, campos, estados, avisos y diálogo comunes. Sus contratos y reglas de teclado están en [Componentes visuales](../docs/componentes-visuales.md). Con Vite activo, el banco sintético está en `http://127.0.0.1:5173/tests/fixtures/components.html`; queda fuera del router y de la compilación pública. No abrir `index.html` directamente como archivo para ejecutar Vue.

Para examinar la compilación integrada, ejecutar `scripts/preparar-web.ps1` desde la raíz con el proceso web detenido. Después `npm run preview`, desde esta carpeta, inicia Django en `http://127.0.0.1:8000/` mediante PowerShell 7. Este comando sustituye la vista previa aislada de Vite: la compilación utiliza `/static/entrepares/`, mientras las rutas de Vue permanecen en la raíz. Consulta [Entrega web](../docs/entrega-web.md); reiniciar Django tras preparar otra versión.
