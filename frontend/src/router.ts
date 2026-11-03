import { createRouter, createWebHistory } from 'vue-router';
import type { RouterHistory, RouteRecordRaw } from 'vue-router';

export const routes: RouteRecordRaw[] = [
  { path: '/', name: 'home', component: () => import('./features/home/HomeView.vue'), meta: { title: 'Personas y proyectos para colaborar' } },
  { path: '/acerca-de', name: 'about', component: () => import('./features/home/AboutView.vue'), meta: { title: 'La idea detrás de Entrepares' } },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('./features/home/NotFoundView.vue'), meta: { title: 'Página no encontrada' } },
];

export function createAppRouter(history: RouterHistory = createWebHistory()) {
  const router = createRouter({
    history, routes,
    scrollBehavior(to, _from, saved) {
      if (saved) return saved;
      return /^#[A-Za-z0-9_-]+$/.test(to.hash) ? { el: to.hash, top: 24 } : { top: 0 };
    },
  });
  router.afterEach((to) => {
    if (typeof document !== 'undefined') document.title = `${to.meta.title} · Entrepares`;
  });
  return router;
}
