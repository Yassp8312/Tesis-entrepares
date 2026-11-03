<script setup lang="ts">
import { RouterLink } from 'vue-router';
import BrandIcon from '../../components/BrandIcon.vue';
</script>

<template>
  <section class="container not-found"><p class="error-number" aria-hidden="true">404</p><p class="eyebrow">PÁGINA NO ENCONTRADA</p><h1>No encontramos<br />la página que buscas.</h1><p class="lead">Puedes volver al inicio y seguir conociendo Entrepares.</p><RouterLink class="button" to="/">Volver al inicio <BrandIcon name="flecha" /></RouterLink></section>
</template>
