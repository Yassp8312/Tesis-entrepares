<script setup lang="ts">
import sprite from '../assets/brand/icons.svg';
defineProps<{ name: 'flecha' | 'menu' | 'cerrar' | 'personas' | 'proyecto' | 'calendario' | 'externo' }>();
</script>

<template>
  <svg class="brand-icon" aria-hidden="true" focusable="false"><use :href="`${sprite}#ep-${name}`" /></svg>
</template>
