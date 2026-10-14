import { createRouter, createWebHashHistory } from 'vue-router'
import { auth } from './auth'
import Home from './pages/Home.vue'
import Author from './pages/Author.vue'
import Play from './pages/Play.vue'
import Feedback from './pages/Feedback.vue'
import AdminFeedback from './pages/AdminFeedback.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', component: Home },
    { path: '/author/:id?', component: Author },
    { path: '/play/:gid', component: Play },
    { path: '/feedback', component: Feedback },
    { path: '/admin/feedback', component: AdminFeedback, meta: { admin: true } },
  ],
})

// Admin route guard: non-admins are sent home (the backend still enforces access; this is just UX)
router.beforeEach((to) => {
  if (to.meta.admin && !(auth.user && auth.user.is_admin)) return '/'
  return true
})

export default router
