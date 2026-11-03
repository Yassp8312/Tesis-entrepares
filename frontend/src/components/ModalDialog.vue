<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue';
import BrandIcon from './BrandIcon.vue';

const props = defineProps<{ modelValue: boolean; title: string; description?: string }>();
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; close: [] }>();
const dialog = ref<HTMLDialogElement | null>(null);
const heading = ref<HTMLHeadingElement | null>(null);
const id = useId();
const titleId = `ep-dialog-${id}-title`;
const descriptionId = computed(() => props.description?.trim() ? `ep-dialog-${id}-description` : undefined);
let returnFocus: HTMLElement | null = null;

function restoreFocus() {
  if (returnFocus?.isConnected) returnFocus.focus({ preventScroll: true });
  returnFocus = null;
}
function sync() {
  const element = dialog.value;
  if (!element) return;
  if (props.modelValue && !element.open) {
    returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    element.showModal();
    heading.value?.focus({ preventScroll: true });
  } else if (!props.modelValue && element.open) element.close();
}
function requestClose() { emit('update:modelValue', false); }
function containTab(event: KeyboardEvent) {
  if (event.key !== 'Tab' || !dialog.value?.open) return;
  const controls = [...dialog.value.querySelectorAll<HTMLElement>('a[href], button, input, select, textarea, [tabindex], [contenteditable="true"], summary')]
    .filter((element) => element.tabIndex >= 0 && !element.matches(':disabled') && element.getClientRects().length > 0 && getComputedStyle(element).visibility !== 'hidden');
  const first = controls[0];
  const last = controls.at(-1);
  const current = document.activeElement;
  if (!first || !last) {
    event.preventDefault();
    heading.value?.focus();
  } else if (event.shiftKey && (current === first || !controls.includes(current as HTMLElement))) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && (current === last || !controls.includes(current as HTMLElement))) {
    event.preventDefault();
    first.focus();
  }
}
function nativeClose() {
  if (props.modelValue) emit('update:modelValue', false);
  restoreFocus();
  emit('close');
}
watch(() => props.modelValue, sync, { flush: 'post' });
onMounted(sync);
onBeforeUnmount(() => { dialog.value?.close(); restoreFocus(); });
</script>

<template>
  <dialog ref="dialog" class="ep-dialog" aria-modal="true" :aria-labelledby="titleId" :aria-describedby="descriptionId"
    @cancel.prevent="requestClose" @close="nativeClose" @keydown="containTab">
    <header class="ep-dialog-header"><h2 ref="heading" :id="titleId" tabindex="-1">{{ title }}</h2>
      <button type="button" class="ep-icon-button" aria-label="Cerrar diálogo" @click="requestClose"><BrandIcon name="cerrar" /></button>
    </header>
    <p v-if="descriptionId" :id="descriptionId" class="ep-dialog-description">{{ description }}</p>
    <div class="ep-dialog-body"><slot /></div>
    <footer v-if="$slots.footer" class="ep-dialog-footer"><slot name="footer" /></footer>
  </dialog>
</template>
