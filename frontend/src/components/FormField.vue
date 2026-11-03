<script setup lang="ts">
import { computed, useId } from 'vue';
import BrandIcon from './BrandIcon.vue';

const props = defineProps<{ id?: string; label: string; hint?: string; error?: string; required?: boolean }>();
const generated = useId();
const inputId = computed(() => props.id || `ep-field-${generated}`);
const hintId = computed(() => props.hint?.trim() ? `${inputId.value}-hint` : undefined);
const errorId = computed(() => props.error?.trim() ? `${inputId.value}-error` : undefined);
const describedBy = computed(() => [hintId.value, errorId.value].filter(Boolean).join(' ') || undefined);
</script>

<template>
  <div class="ep-field" :class="{ 'ep-field--invalid': errorId }">
    <label :for="inputId">{{ label }} <span v-if="required" class="ep-required">(obligatorio)</span></label>
    <slot :input-id="inputId" :described-by="describedBy" :invalid="errorId ? true : undefined" />
    <p v-if="hintId" :id="hintId" class="ep-field-hint">{{ hint }}</p>
    <p v-if="errorId" :id="errorId" class="ep-field-error"><BrandIcon name="alerta" />{{ error }}</p>
  </div>
</template>
