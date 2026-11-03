<script setup lang="ts">
import { RouterLink } from 'vue-router';
import BrandIcon from '../../components/BrandIcon.vue';
import symbol from '../../assets/brand/symbol.svg';
</script>

<template>
  <div class="container">
    <section class="hero" aria-labelledby="hero-title">
      <div class="hero-copy">
        <p class="eyebrow">COLABORACIÓN ACADÉMICA Y PROFESIONAL · CUBA</p>
        <h1 id="hero-title">Tu proyecto necesita <em>otras disciplinas.</em></h1>
        <p class="lead">Las buenas ideas crecen cuando encuentran con quién. Estamos construyendo un espacio para conectar personas con conocimientos complementarios y proyectos que necesitan distintas miradas.</p>
        <RouterLink class="button" to="/acerca-de">Conoce la propuesta <BrandIcon name="flecha" /></RouterLink>
        <p class="availability">La comunidad se está preparando. El registro aún no está disponible.</p>
      </div>
      <div class="meeting-panel" aria-label="Un punto de encuentro entre disciplinas">
        <div class="panel-top"><span class="eyebrow">PUNTO DE ENCUENTRO</span><span class="small-index">01 — ∞</span></div>
        <img class="meeting-symbol" :src="symbol" width="188" height="188" alt="Dos piezas iguales dejan un espacio abierto entre ellas" />
        <p class="panel-title">Distintas miradas.<br /><em>Una idea en común.</em></p>
        <div class="disciplines"><span>Informática</span><span>Salud</span><span>Diseño</span></div>
        <div class="panel-bottom"><span>Cada persona aporta una mirada.</span><BrandIcon name="personas" /></div>
      </div>
    </section>
    <section class="meeting-section" aria-labelledby="meeting-title">
      <div class="section-heading"><div><p class="eyebrow">PERSONAS · IDEAS · PROYECTOS</p><h2 id="meeting-title">El punto de partida es encontrarse.</h2></div><p>Más allá del aula, de la carrera<br class="desktop-break" /> y de la universidad.</p></div>
      <ol class="editorial-list">
        <li><span class="list-number">01</span><div><h3>Personas con otras miradas</h3><p>Una comunidad de estudiantes y graduados para encontrar conocimientos, intereses y experiencias que se complementen.</p></div><RouterLink to="/acerca-de#personas" aria-label="Conocer la propuesta de comunidad"><BrandIcon name="flecha" /></RouterLink></li>
        <li><span class="list-number">02</span><div><h3>Proyectos que necesitan un equipo</h3><p>Oportunidades de colaboración académica y del sector productivo, con el contacto directo de sus responsables.</p></div><RouterLink to="/acerca-de#oportunidades" aria-label="Conocer la propuesta de oportunidades"><BrandIcon name="flecha" /></RouterLink></li>
        <li><span class="list-number">03</span><div><h3>Conocimiento que sigue circulando</h3><p>Un espacio para compartir avances, resultados y eventos que acerquen a quienes están investigando.</p></div><RouterLink to="/acerca-de#novedades" aria-label="Conocer la propuesta de novedades"><BrandIcon name="flecha" /></RouterLink></li>
      </ol>
    </section>
  </div>
</template>
