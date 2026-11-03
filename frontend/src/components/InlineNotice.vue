<script setup lang="ts">
import { computed } from 'vue';
import BrandIcon from './BrandIcon.vue';
import type { IconName, Tone } from './types.ts';
const props = withDefaults(defineProps<{
  title: string; message: string; tone?: Tone; announce?: 'off' | 'polite' | 'assertive'; dismissible?: boolean;
}>(), { tone: 'info', announce: 'off' });
defineEmits<{ dismiss: [] }>();
const icon = computed<IconName>(() => props.tone === 'success' ? 'comprobar' : ['danger', 'warning'].includes(props.tone) ? 'alerta' : 'informacion');
</script>

<template>
  <div class="ep-notice" :class="`ep-tone--${tone}`"
    :role="announce === 'assertive' ? 'alert' : announce === 'polite' ? 'status' : undefined"
    :aria-live="announce === 'off' ? undefined : announce" :aria-atomic="announce === 'off' ? undefined : 'true'">
    <BrandIcon :name="icon" />
    <div class="ep-notice-copy"><p class="ep-notice-title">{{ title }}</p><p>{{ message }}</p></div>
    <button v-if="dismissible" type="button" class="ep-icon-button" :aria-label="`Cerrar aviso: ${title}`" @click="$emit('dismiss')"><BrandIcon name="cerrar" /></button>
  </div>
</template>
