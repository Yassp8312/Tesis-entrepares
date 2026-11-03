<script setup lang="ts">
import ActionLink from '../../components/ActionLink.vue';
</script>

<template>
  <section class="container not-found"><p class="error-number" aria-hidden="true">404</p><p class="eyebrow">PÁGINA NO ENCONTRADA</p><h1>No encontramos<br />la página que buscas.</h1><p class="lead">Puedes volver al inicio y seguir conociendo Entrepares.</p><ActionLink to="/" label="Volver al inicio" icon="flecha" /></section>
</template>
