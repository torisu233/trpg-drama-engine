import { createRouter, createWebHashHistory } from 'vue-router'
import Home from './pages/Home.vue'
import Author from './pages/Author.vue'
import Play from './pages/Play.vue'

export default createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', component: Home },
    { path: '/author/:id?', component: Author },
    { path: '/play/:gid', component: Play },
  ],
})
