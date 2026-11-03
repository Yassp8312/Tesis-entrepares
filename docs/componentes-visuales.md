# Componentes visuales comunes

SP01-T08, 3 de noviembre de 2026. La biblioteca de `frontend/src/components` conserva la propuesta de identidad v1: papel, tinta y terracota; Lora para titulares y Source Sans 3 para lectura y controles. Reutiliza los tokens, iconos SVG, fuentes y licencias locales incorporados en T07. No añade dependencias, servicios externos ni funciones de negocio.

Trazabilidad: WI06/WI30, DV03/DV06, RNF07/RNF08/RNF11 y evidencia técnica parcial de AT16. Completar esta tarea no cierra esos trabajos transversales ni la evaluación de usabilidad del piloto.

## Contratos de los componentes

| Componente | Uso y contrato |
| --- | --- |
| `BaseButton` | Acción nativa. `label` obligatorio; `type` es `button` por omisión y admite `submit`/`reset`. Variantes `primary`, `secondary`, `text`, `danger`; tamaños `regular`/`small`. `disabled` y `loading` impiden la activación; carga muestra `loadingLabel` y `aria-busy`. Emite `click` con el evento nativo. |
| `ActionLink` | Navegación interna con `to`, `label`, variante e icono opcional. Conserva un enlace real de Vue Router y no simula un botón deshabilitado. Para un destino externo, utilizar un enlace HTML con sus atributos correspondientes. |
| `FormField` | Contenedor de etiqueta, obligatoriedad, ayuda y error. Genera identificadores con `useId` o utiliza `id` explícito. El slot entrega `inputId`, `describedBy` e `invalid` para asociar un control. |
| `TextField` | `v-model` de texto, etiqueta, ayuda, error, obligatoriedad y deshabilitación. Tipos `text`, `email`, `password`, `search`, `tel`, `url`. Los atributos y eventos adicionales llegan al input nativo; expone `focus()`. |
| `TextAreaField` | Mismo contrato de texto y accesibilidad; añade `rows`, permite redimensionar verticalmente y expone `focus()`. |
| `SelectField` | `v-model` de texto y opciones `{ value, label, disabled? }`. Selección nativa; marcador inicial deshabilitado cuando es obligatorio. Conserva atributos, ayuda, error y `focus()`. |
| `StatusBadge` | Estado expresado mediante `label`, tono y un icono opcional. No es interactivo ni anuncia cambios automáticamente. No decide verificación, distinciones o permisos. |
| `InlineNotice` | `title`, `message`, tono y cierre opcional. `announce` es `off` por omisión; `polite` usa estado y `assertive` alerta. `dismiss` solicita al propietario retirar el aviso; el componente no cambia datos. |
| `ModalDialog` | Diálogo nativo controlado mediante `v-model`, con título obligatorio, descripción opcional, cuerpo y slot `footer`. Emite `update:modelValue` para solicitar cierre y `close` al recibir el cierre nativo. |
| `BrandIcon` | Icono decorativo tipado entre los 24 nombres del sprite local. Se oculta de la lectura asistida. Los controles que solo muestran un icono necesitan un nombre accesible propio. |

Los tonos son `neutral`, `info`, `success`, `warning` y `danger`. El contenido visible se proporciona mediante texto escapado por Vue, sin `v-html`. Los identificadores explícitos deben ser únicos; los valores de opciones también. Las clases `ep-*` y `components.css` centralizan la apariencia; cada pantalla se responsabiliza de su distribución.

## Formularios y avisos

```vue
<TextField ref="emailControl" v-model="email" label="Correo electrónico"
  type="email" name="email" autocomplete="email" required
  hint="Introduce el correo asociado a tu cuenta." :error="emailError" />
<BaseButton type="submit" label="Guardar cambios" :loading="saving"
  loading-label="Guardando cambios…" />
```

`required` conserva la semántica nativa. La validación de dominio, las longitudes de contrato y la autorización pertenecen a la funcionalidad y al servidor. Los controles no deducen errores a partir de la edición: la pantalla proporciona y retira `error` según su validación. Al fallar un envío, debe presentar un resumen y llevar el foco al primer error o al resumen. `aria-describedby` externo se combina sin duplicados con la ayuda y el error del componente.

Para un resultado dinámico ordinario puede usarse `announce="polite"`; reservar `assertive` para mensajes urgentes. Los mensajes que ya existen al entrar en una página permanecen estáticos. No depender solo del color para expresar un estado, ni convertir cada mensaje de campo en una alerta simultánea. Si se retira un aviso mediante su botón, la pantalla debe elegir un destino de foco cuando el flujo lo necesite.

## Diálogo y teclado

`showModal()` activa el comportamiento modal del navegador. Al abrir, el título recibe el foco y el diálogo queda asociado a su título y descripción. Tab y Mayús+Tab recorren los controles habilitados y visibles y vuelven a empezar dentro del diálogo; el cálculo se actualiza en cada pulsación. Escape y el botón de cierre solicitan cambiar `v-model` a `false`. Una acción del footer puede hacer lo mismo.

Al cerrarse, se devuelve el foco al elemento que lo abrió, si continúa conectado. También se restaura al desmontar. Si el flujo elimina ese elemento, la pantalla debe enfocar un destino lógico que permanezca disponible. Los slots deben evitar índices de tabulación positivos y gestionar el foco de sus controles dinámicos. No se cierra al pulsar el fondo; no hay confirmaciones, guardado ni llamadas HTTP implícitas.

## Comprobaciones reproducibles

Desde `frontend`:

```powershell
npm run typecheck
npm test
npm run build
npm run dev
```

El banco sintético se abre por HTTP en `http://127.0.0.1:5173/tests/fixtures/components.html`. No necesita Django y no envía datos. Abrir directamente `frontend/index.html` como archivo no inicia la aplicación Vue: se necesita Vite o el servidor del despliegue. El banco vive en `tests/fixtures`, está fuera del router público y no forma parte de la compilación de producción.

Se ejecutaron **67 pruebas sin fallos ni omisiones**: 37 existentes de cliente/configuración, 15 de estructura de componentes y 15 de contraste. Vite compila los componentes para renderizado de prueba con `vue/server-renderer`; ese renderizado comprueba semántica, asociación de etiquetas, identificadores, escape, atributos y estados. No sustituye las interacciones del navegador. Los 15 pares de tokens alcanzan al menos 4,5:1 para los textos examinados y 3:1 para los bordes de controles examinados, sin redondear para decidir el cumplimiento.

En el navegador interno se comprobaron activación, carga/deshabilitación, edición, selección, error asociado y foco, cierre de aviso, apertura modal, recorrido Tab/Mayús+Tab, Escape, cierre explícito, confirmación, cierre desde el padre y desmontaje con devolución de foco. Una primera revisión detectó salida de foco en los extremos del diálogo; se añadió contención explícita y se repitió ese recorrido con resultado correcto.

Se revisaron 1280, 390 y 320 px sin desbordamiento horizontal. Los controles comunes visibles examinados tienen al menos 44 px de altura; los campos y botones regulares, 48 px. El diálogo cabe en las pantallas móviles examinadas. Se comprobó además la compilación con Vite preview: enlaces de portada y página no encontrada, y aviso estático de presentación. No se observaron errores ni advertencias de consola. Se restableció el viewport temporal al terminar.

Los resultados compactos están en [componentes-visuales.json](evidencias/componentes-visuales.json); capturas y registros locales en `.cache/componentes`, excluidos de Git. Tipos y compilación pasaron; los bloqueos, dependencias, backend, siete fuentes de diseño y doce recursos de marca permanecen sin cambios. Estas comprobaciones no acreditan WCAG completo, todos los navegadores, lectores de pantalla, usabilidad con participantes ni las tareas U01–U08 del piloto. AT16 conserva estado parcial.

## Continuación

SP01-T09 preparará `collectstatic`, documento inicial y retorno de navegación desde Django, conservando la separación de `/api/`, `/admin/` y `/static/`. Los formularios y diálogos funcionales se incorporarán al implementar sus casos de uso; no se han simulado registros, perfiles o permisos.

## Referencias

- [Registro de fuentes y planificación](base-documental.json) y [procedencia de marca](evidencias/recursos-marca-iniciales.json).
- [Vue: identificadores de accesibilidad con useId](https://vuejs.org/api/composition-api-helpers.html#useid).
- [WAI: patrón de diálogo modal](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/).
- [WCAG: contraste mínimo de texto](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).
- [MDN: elemento dialog](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/dialog).
