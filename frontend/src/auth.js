// Auth state: JWT token + current user. Token lives in localStorage; requests send Authorization: Bearer.
import { reactive } from 'vue'

export const auth = reactive({
  token: localStorage.getItem('token') || '',
  user: null,      // { username, is_admin }
  ready: false,    // whether the initial /auth/me probe has finished
})

export function setSession(token, user) {
  auth.token = token
  auth.user = user
  localStorage.setItem('token', token)
}

export function clearSession() {
  auth.token = ''
  auth.user = null
  localStorage.removeItem('token')
}

export const isAdmin = () => !!(auth.user && auth.user.is_admin)
