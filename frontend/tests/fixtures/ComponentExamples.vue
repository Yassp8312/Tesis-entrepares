<script setup lang="ts">
import { nextTick, ref } from 'vue';
import BaseButton from '../../src/components/BaseButton.vue';
import TextField from '../../src/components/TextField.vue';
import TextAreaField from '../../src/components/TextAreaField.vue';
import SelectField from '../../src/components/SelectField.vue';
import StatusBadge from '../../src/components/StatusBadge.vue';
import InlineNotice from '../../src/components/InlineNotice.vue';
import ModalDialog from '../../src/components/ModalDialog.vue';

const count = ref(0);
const loading = ref(false);
const email = ref('');
const discipline = ref('');
const description = ref('');
const errors = ref(false);
const notice = ref(true);
const modal = ref(false);
const removed = ref(false);
const modalNote = ref('');
const emailControl = ref<InstanceType<typeof TextField> | null>(null);
async function showErrors() { errors.value = true; await nextTick(); emailControl.value?.focus(); }
</script>

<template>
  <main class="container examples" id="ejemplos">
    <header><p class="eyebrow">ENTREPARES · BANCO LOCAL DE PRUEBAS</p><h1>Una misma voz en cada detalle.</h1><p class="lead">Solo datos sintéticos. Esta página no registra personas, no publica contenido y no envía formularios.</p></header>
    <div class="example-grid">
      <section aria-labelledby="actions-title"><h2 id="actions-title">Acciones</h2>
        <div class="example-actions"><BaseButton label="Acción de ejemplo" icon="flecha" @click="count++" /><BaseButton label="Acción secundaria" variant="secondary" /><BaseButton label="No disponible" disabled /></div>
        <p><output aria-live="polite">Activaciones: {{ count }}</output></p>
        <label class="example-toggle"><input type="checkbox" v-model="loading" />Mostrar estado de carga</label>
        <BaseButton label="Guardar ejemplo" :loading="loading" loading-label="Guardando ejemplo…" @click="count++" />
        <h2>Estados</h2><div class="example-actions"><StatusBadge label="Dato de ejemplo" /><StatusBadge label="Información de ejemplo" tone="info" icon="informacion" /><StatusBadge label="Resultado de ejemplo" tone="success" icon="comprobar" /><StatusBadge label="Revisión de ejemplo" tone="warning" icon="tiempo" /><StatusBadge label="Error de ejemplo" tone="danger" icon="alerta" /></div>
        <h2>Avisos</h2><InlineNotice v-if="notice" title="Aviso de prueba" message="Este contenido es un ejemplo para comprobar lectura y cierre." tone="info" announce="polite" dismissible @dismiss="notice = false" />
        <InlineNotice title="Error de prueba" message="Este mensaje comprueba el contraste y la descripción del error." tone="danger" />
      </section>
      <section aria-labelledby="fields-title"><h2 id="fields-title">Campos</h2>
        <div class="example-fields">
          <TextField ref="emailControl" v-model="email" label="Correo de ejemplo" type="email" name="synthetic-email" autocomplete="off" required hint="Usa una dirección ficticia del dominio example.org." :error="errors ? 'Revisa el correo de ejemplo.' : undefined" />
          <SelectField v-model="discipline" label="Disciplina de ejemplo" :options="[{value:'ici',label:'Informática'},{value:'med',label:'Medicina'}]" required hint="Selección sintética para las pruebas." :error="errors ? 'Selecciona una disciplina de ejemplo.' : undefined" />
          <TextAreaField v-model="description" label="Descripción de ejemplo" maxlength="200" hint="Hasta 200 caracteres; no se envían a un servidor." />
          <TextField model-value="Dato sintético" label="Campo no editable" disabled />
          <BaseButton label="Mostrar errores de ejemplo" variant="secondary" @click="showErrors" />
        </div>
      </section>
    </div>
    <section class="example-dialog-controls"><h2>Diálogo</h2><div class="example-actions"><BaseButton label="Abrir diálogo de ejemplo" @click="modal = true" /><BaseButton v-if="!removed" label="Abrir diálogo desmontable" variant="secondary" @click="modal = true" /><BaseButton label="Restablecer diálogo de ejemplo" variant="text" @click="removed = false" /></div>
      <p>El diálogo permite probar Escape, tabulación, confirmación y retorno del foco.</p>
    </section>
    <ModalDialog v-if="!removed" v-model="modal" title="Confirmar ejemplo" description="Este diálogo solo modifica el estado de esta página de pruebas.">
      <TextField v-model="modalNote" label="Nota de ejemplo" hint="No se guarda ni se envía." />
      <template #footer><BaseButton label="Volver al ejemplo" variant="secondary" @click="modal = false" /><BaseButton label="Confirmar ejemplo" @click="modal = false; count++" /><BaseButton label="Desmontar ejemplo" variant="text" @click="removed = true; modal = false" /></template>
    </ModalDialog>
    <footer class="example-footer"><a href="https://jorge-coffee.onrender.com/" target="_blank" rel="noopener noreferrer">Apoyar a Jorge</a></footer>
  </main>
</template>

<style>
.examples { padding-block: 44px; }
.examples header .lead { margin-top: 20px; max-width: 850px; }
.examples h1 { font-size: clamp(34px,4vw,48px); margin-top: 14px; }
.examples h2 { font-size: 28px; margin-block: 28px 18px; }
.example-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 48px; }
.example-grid > section { min-width: 0; }
.example-actions { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin-bottom: 16px; }
.example-toggle { display: flex; align-items: center; gap: 10px; min-height: 44px; margin-block: 12px; }
.example-toggle input { width: 20px; height: 20px; }
.example-fields { display: grid; gap: 20px; }
.examples .ep-notice + .ep-notice { margin-top: 16px; }
.example-dialog-controls { border-top: 1px solid var(--ep-control); margin-top: 36px; }
.example-footer { margin-top: 44px; font-size: 14px; }
.example-footer a { display: inline-flex; align-items: center; min-height: 44px; text-underline-offset: 4px; }
@media(max-width: 800px) { .example-grid { grid-template-columns: 1fr; gap: 12px; } }
</style>
