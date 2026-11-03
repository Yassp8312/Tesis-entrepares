import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { createServer } from 'vite';
import type { ViteDevServer } from 'vite';

let server: ViteDevServer;
let render: (name: string, props: Record<string, unknown>) => Promise<string>;
let renderFields: () => Promise<string>;
before(async () => {
  server = await createServer({ server: { middlewareMode: true, hmr: false, watch: null }, appType: 'custom' });
  ({ render, renderFields } = await server.ssrLoadModule('/tests/render-components.ts'));
});
after(async () => { await server?.close(); });

test('el botón es una acción con tipo seguro y texto escapado', async () => {
  const html = await render('BaseButton', { label: '<script>ejemplo</script>' });
  assert.match(html, /<button[^>]*type="button"/);
  assert.match(html, /&lt;script&gt;ejemplo&lt;\/script&gt;/);
  assert.doesNotMatch(html, /disabled|aria-busy/);
});

test('carga y deshabilitación impiden nuevas activaciones y conservan un nombre', async () => {
  const html = await render('BaseButton', { label: 'Guardar', loading: true, loadingLabel: 'Guardando ejemplo…' });
  assert.match(html, /disabled/); assert.match(html, /aria-busy="true"/);
  assert.match(html, /Guardando ejemplo…/); assert.doesNotMatch(html, />Guardar</);
});

test('una navegación conserva semántica de enlace', async () => {
  const html = await render('ActionLink', { label: 'Conocer', to: '/acerca-de', icon: 'flecha' });
  assert.match(html, /<a[^>]*href="\/acerca-de"/); assert.doesNotMatch(html, /<button/);
  assert.match(html, /aria-hidden="true"/);
});

test('los campos generan etiquetas y descripciones sin identificadores repetidos', async () => {
  const html = await renderFields();
  const identifiers = [...html.matchAll(/\sid="([^"]+)"/g)].map(match => match[1]);
  assert.equal(new Set(identifiers).size, identifiers.length);
  for (const match of html.matchAll(/for="([^"]+)"/g)) assert.ok(identifiers.includes(match[1]));
  for (const match of html.matchAll(/aria-describedby="([^"]+)"/g)) {
    for (const id of match[1].split(' ')) assert.ok(identifiers.includes(id));
  }
  assert.match(html, /aria-invalid="true"/); assert.match(html, /Texto &lt;sintético&gt;/);
});

test('atributos de formulario llegan al input y se preservan descripciones externas', async () => {
  const html = await render('TextField', { label: 'Correo', modelValue: 'sintetico@example.org', id: 'correo-prueba', type: 'email', name: 'email', autocomplete: 'email', maxlength: 254, hint: 'Ayuda', required: true, 'aria-describedby': 'contexto-externo' });
  assert.match(html, /<input[^>]*name="email"/); assert.match(html, /type="email"/);
  assert.match(html, /maxlength="254"/); assert.match(html, /required/);
  assert.match(html, /for="correo-prueba"/); assert.match(html, /aria-describedby="contexto-externo correo-prueba-hint"/);
});

test('selección y deshabilitación mantienen semántica nativa', async () => {
  const html = await render('SelectField', { label: 'Disciplina', modelValue: 'med', disabled: true, options: [{ value: 'ici', label: 'Informática' }, { value: 'med', label: 'Medicina' }] });
  assert.match(html, /<select[^>]*disabled/); assert.match(html, /value="med" selected/);
});

for (const tone of ['neutral', 'info', 'success', 'warning', 'danger']) {
  test(`estado ${tone} usa texto explícito y no inventa una verificación`, async () => {
    const html = await render('StatusBadge', { label: 'Estado sintético', tone, icon: 'informacion' });
    assert.match(html, /Estado sintético/); assert.match(html, /aria-hidden="true"/);
    assert.doesNotMatch(html, /Verificad|role="alert"|tabindex/);
  });
}

for (const [announce, role] of [['off', null], ['polite', 'status'], ['assertive', 'alert']] as const) {
  test(`aviso ${announce} declara su anuncio sin depender solo del color`, async () => {
    const html = await render('InlineNotice', { title: 'Aviso sintético', message: '<dato>', tone: 'danger', announce, dismissible: true });
    if (role) assert.match(html, new RegExp(`role="${role}"`)); else assert.doesNotMatch(html, /role="alert"|aria-live/);
    assert.match(html, /&lt;dato&gt;/); assert.match(html, /aria-label="Cerrar aviso: Aviso sintético"/);
  });
}

test('el diálogo tiene título y descripción asociados, cierre y semántica nativa', async () => {
  const html = await render('ModalDialog', { modelValue: false, title: 'Ejemplo de diálogo', description: 'Descripción sintética' });
  assert.match(html, /<dialog/); assert.match(html, /aria-modal="true"/);
  assert.match(html, /aria-labelledby="[^"]+"/); assert.match(html, /aria-describedby="[^"]+"/);
  assert.match(html, /aria-label="Cerrar diálogo"/); assert.doesNotMatch(html, /<dialog[^>]*\sopen/);
});
