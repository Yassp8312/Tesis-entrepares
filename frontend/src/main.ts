import { createApp } from 'vue';
import App from './App.vue';
import { createAppRouter } from './router.ts';
import './assets/tokens.css';
import './assets/app.css';
import './components/components.css';

const router = createAppRouter();
const app = createApp(App);
app.use(router);
await router.isReady();
app.mount('#app');
