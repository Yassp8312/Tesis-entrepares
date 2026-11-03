<script setup lang="ts">
import BrandIcon from './BrandIcon.vue';
import type { IconName, Tone } from './types.ts';
withDefaults(defineProps<{ label: string; tone?: Tone; icon?: IconName }>(), { tone: 'neutral' });
</script>

<template>
  <span class="ep-badge" :class="`ep-tone--${tone}`"><BrandIcon v-if="icon" :name="icon" />{{ label }}</span>
</template>
