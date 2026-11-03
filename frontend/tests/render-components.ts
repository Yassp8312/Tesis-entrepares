import { createSSRApp, h } from 'vue';
import { renderToString } from 'vue/server-renderer';
import { createMemoryHistory, createRouter } from 'vue-router';
import type { Component, VNode } from 'vue';
import BaseButton from '../src/components/BaseButton.vue';
import ActionLink from '../src/components/ActionLink.vue';
import TextField from '../src/components/TextField.vue';
import TextAreaField from '../src/components/TextAreaField.vue';
import SelectField from '../src/components/SelectField.vue';
import StatusBadge from '../src/components/StatusBadge.vue';
import InlineNotice from '../src/components/InlineNotice.vue';
import ModalDialog from '../src/components/ModalDialog.vue';

const components: Record<string, Component> = { BaseButton, ActionLink, TextField, TextAreaField, SelectField, StatusBadge, InlineNotice, ModalDialog };
export async function render(name: string, props: Record<string, unknown>) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { render: () => null }, meta: { title: 'Prueba' } }, { path: '/acerca-de', component: { render: () => null }, meta: { title: 'Prueba' } }] });
  await router.push('/');
  const app = createSSRApp({ render: () => h(components[name], props) });
  app.use(router);
  return renderToString(app);
}

export async function renderFields() {
  const app = createSSRApp({ render: () => h('div', [
    h(TextField, { label: 'Primer campo', modelValue: '', hint: 'Ayuda de prueba', error: 'Error de prueba' }),
    h(TextField, { label: 'Segundo campo', modelValue: 'sintético' }),
    h(TextAreaField, { label: 'Texto de prueba', modelValue: 'Texto <sintético>' }),
  ] as VNode[]) });
  return renderToString(app);
}
