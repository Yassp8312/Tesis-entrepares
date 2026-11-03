<script setup lang="ts">
import { computed, ref } from 'vue';
import FormField from './FormField.vue';
import { descriptionIds } from './types.ts';

defineOptions({ inheritAttrs: false });
const props = withDefaults(defineProps<{
  modelValue: string; label: string; id?: string; hint?: string; error?: string;
  rows?: number; required?: boolean; disabled?: boolean;
}>(), { rows: 4 });
const emit = defineEmits<{ 'update:modelValue': [value: string] }>();
const value = computed({ get: () => props.modelValue, set: next => emit('update:modelValue', next) });
const control = ref<HTMLTextAreaElement | null>(null);
defineExpose({ focus: () => control.value?.focus() });
</script>

<template>
  <FormField :id="id" :label="label" :hint="hint" :error="error" :required="required"
    v-slot="{ inputId, describedBy, invalid }">
    <textarea v-bind="$attrs" ref="control" v-model="value" class="ep-control" :id="inputId" :rows="rows"
      :required="required" :disabled="disabled" :aria-invalid="invalid"
      :aria-describedby="descriptionIds($attrs['aria-describedby'], describedBy)" />
  </FormField>
</template>
