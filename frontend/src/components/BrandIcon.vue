<script setup lang="ts">
import sprite from '../assets/brand/icons.svg';
import type { IconName } from './types.ts';
defineProps<{ name: IconName }>();
</script>

<template>
  <svg class="brand-icon" aria-hidden="true" focusable="false"><use :href="`${sprite}#ep-${name}`" /></svg>
</template>
