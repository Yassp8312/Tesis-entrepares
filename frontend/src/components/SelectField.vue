<script setup lang="ts">
import { computed, ref } from 'vue';
import FormField from './FormField.vue';
import { descriptionIds } from './types.ts';

defineOptions({ inheritAttrs: false });
const props = withDefaults(defineProps<{
  modelValue: string; label: string; id?: string; hint?: string; error?: string;
  options: { value: string; label: string; disabled?: boolean }[];
  placeholder?: string; required?: boolean; disabled?: boolean;
}>(), { placeholder: 'Selecciona una opción' });
const emit = defineEmits<{ 'update:modelValue': [value: string] }>();
const value = computed({ get: () => props.modelValue, set: next => emit('update:modelValue', next) });
const control = ref<HTMLSelectElement | null>(null);
defineExpose({ focus: () => control.value?.focus() });
</script>

<template>
  <FormField :id="id" :label="label" :hint="hint" :error="error" :required="required"
    v-slot="{ inputId, describedBy, invalid }">
    <select v-bind="$attrs" ref="control" v-model="value" class="ep-control" :id="inputId"
      :required="required" :disabled="disabled" :aria-invalid="invalid"
      :aria-describedby="descriptionIds($attrs['aria-describedby'], describedBy)">
      <option value="" :disabled="required">{{ placeholder }}</option>
      <option v-for="option in options" :key="option.value" :value="option.value" :disabled="option.disabled">{{ option.label }}</option>
    </select>
  </FormField>
</template>
