<script setup lang="ts">
import { RouterLink } from 'vue-router';
import BrandIcon from '../../components/BrandIcon.vue';
</script>

<template>
  <div class="container about-page">
    <RouterLink class="text-link back-link" to="/">Volver al inicio</RouterLink>
    <header class="about-heading"><p class="eyebrow">LA IDEA DETRÁS DE ENTREPARES</p><h1>Conocer a la persona adecuada cambia <em>lo que puedes hacer.</em></h1><p class="lead">Una investigación puede empezar en una carrera y necesitar conocimientos de muchas otras. Entrepares nace para hacer más sencillo ese encuentro.</p></header>
    <p class="preparation-note">Estamos preparando la plataforma. Estas son las tres partes de la propuesta; las funciones de comunidad y publicación se incorporarán progresivamente.</p>
    <div class="about-sections">
      <section id="personas"><span class="list-number">01</span><div><p class="eyebrow">LA COMUNIDAD</p><h2>Personas con las que construir</h2><p>La bolsa de perfiles permitirá encontrar estudiantes y graduados por disciplina y universidad, conocer su experiencia y descubrir intereses compartidos.</p><p>La información declarada y los respaldos registrados se distinguirán con claridad. La consulta requerirá acceso autorizado, personal u organizacional, y cada persona ofrecerá sus medios de contacto visibles.</p></div></section>
      <section id="oportunidades"><span class="list-number">02</span><div><p class="eyebrow">LAS OPORTUNIDADES</p><h2>Una necesidad puede convertirse en un proyecto</h2><p>Estudiantes, graduados y organizaciones con la verificación correspondiente podrán compartir proyectos que buscan colaboración, indicando qué conocimientos necesitan y cómo contactar a sus responsables.</p><p>Las oportunidades serán públicas y podrán incluir financiación declarada. El contacto se realizará directamente por los medios publicados.</p></div></section>
      <section id="novedades"><span class="list-number">03</span><div><p class="eyebrow">EL CONOCIMIENTO COMPARTIDO</p><h2>Lo que avanza también merece encontrarse</h2><p>Una sección pública de novedades y eventos permitirá compartir el progreso de los proyectos, sus resultados y nuevos espacios de intercambio.</p><p>La idea es que una colaboración abra la puerta a la siguiente.</p></div></section>
    </div>
    <div class="closing-note"><BrandIcon name="personas" /><p>Encontrarnos es el primer paso.<br /><span>Lo que sigue, lo construimos entre pares.</span></p></div>
  </div>
</template>
