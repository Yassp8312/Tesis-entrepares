<script setup lang="ts">
import { nextTick, ref, watch } from 'vue';
import { RouterLink, RouterView, useRoute } from 'vue-router';
import BrandIcon from './components/BrandIcon.vue';
import logo from './assets/brand/logo.svg';
import logoWhite from './assets/brand/logo-white.svg';

const route = useRoute();
const menuOpen = ref(false);
const main = ref<HTMLElement | null>(null);
const menuButton = ref<HTMLButtonElement | null>(null);
watch(() => route.fullPath, async () => {
  menuOpen.value = false;
  await nextTick();
  main.value?.focus({ preventScroll: true });
});
function closeMenu() {
  if (menuOpen.value) { menuOpen.value = false; menuButton.value?.focus(); }
}
async function selectNavigation() {
  menuOpen.value = false;
  await nextTick();
  main.value?.focus({ preventScroll: true });
}
</script>

<template>
  <a class="skip-link" href="#contenido">Saltar al contenido</a>
  <header class="site-header" @keydown.esc="closeMenu">
    <div class="container header-inner">
      <RouterLink class="brand" to="/" aria-label="Entrepares, inicio" @click="selectNavigation"><img :src="logo" alt="Entrepares" width="218" height="40" /></RouterLink>
      <button ref="menuButton" class="menu-button" type="button" :aria-expanded="menuOpen" aria-controls="navegacion" :aria-label="menuOpen ? 'Cerrar menú' : 'Abrir menú'" @click="menuOpen = !menuOpen"><BrandIcon :name="menuOpen ? 'cerrar' : 'menu'" /></button>
      <nav id="navegacion" class="navigation" :class="{ 'is-open': menuOpen }" aria-label="Navegación principal">
        <RouterLink to="/" exact-active-class="is-active" @click="selectNavigation">Inicio</RouterLink>
        <RouterLink to="/acerca-de" active-class="is-active" @click="selectNavigation">La idea</RouterLink>
        <span class="stage"><span aria-hidden="true"></span>En preparación</span>
      </nav>
    </div>
  </header>
  <main id="contenido" ref="main" tabindex="-1"><RouterView /></main>
  <footer class="site-footer">
    <div class="container footer-inner">
      <div><RouterLink to="/" aria-label="Entrepares, inicio"><img :src="logoWhite" width="180" height="34" alt="Entrepares" /></RouterLink><p>Personas y proyectos para colaborar.</p></div>
      <div class="footer-note"><p>Un punto de encuentro entre disciplinas.</p><a href="https://jorge-coffee.onrender.com/" target="_blank" rel="noopener noreferrer">Apoyar a Jorge <BrandIcon name="externo" /></a></div>
    </div>
  </footer>
</template>
