// 登录状态：JWT token + 当前用户。token 存 localStorage，请求带 Authorization: Bearer。
import { reactive } from 'vue'

export const auth = reactive({
  token: localStorage.getItem('token') || '',
  user: null,      // { username, is_admin }
  ready: false,    // 初次探测（/auth/me）是否完成
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
