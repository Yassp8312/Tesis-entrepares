<script setup lang="ts">
import BrandIcon from './BrandIcon.vue';
import type { ButtonVariant, IconName } from './types.ts';

const props = withDefaults(defineProps<{
  label: string;
  type?: 'button' | 'submit' | 'reset';
  variant?: ButtonVariant;
  size?: 'regular' | 'small';
  icon?: IconName;
  disabled?: boolean;
  loading?: boolean;
  loadingLabel?: string;
}>(), { type: 'button', variant: 'primary', size: 'regular', loadingLabel: 'Procesando…' });
const emit = defineEmits<{ click: [event: MouseEvent] }>();
function activate(event: MouseEvent) {
  if (props.disabled || props.loading) { event.preventDefault(); return; }
  emit('click', event);
}
</script>

<template>
  <button :type="type" class="ep-button" :class="[`ep-button--${variant}`, `ep-button--${size}`]"
    :disabled="disabled || loading" :aria-busy="loading ? 'true' : undefined" @click="activate">
    <span v-if="loading" class="ep-spinner" aria-hidden="true"></span>
    <span>{{ loading ? loadingLabel : label }}</span>
    <BrandIcon v-if="icon && !loading" :name="icon" />
  </button>
</template>
