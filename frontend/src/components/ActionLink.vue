<script setup lang="ts">
import { RouterLink } from 'vue-router';
import type { RouteLocationRaw } from 'vue-router';
import BrandIcon from './BrandIcon.vue';
import type { IconName } from './types.ts';

withDefaults(defineProps<{
  to: RouteLocationRaw;
  label: string;
  variant?: 'primary' | 'secondary' | 'text';
  icon?: IconName;
}>(), { variant: 'primary' });
</script>

<template>
  <RouterLink :to="to" class="ep-button" :class="`ep-button--${variant}`">
    <span>{{ label }}</span><BrandIcon v-if="icon" :name="icon" />
  </RouterLink>
</template>
