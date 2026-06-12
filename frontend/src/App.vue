<template>
  <header class="topbar">
    <router-link class="brand" to="/">🎭 跑团工作室</router-link>
    <span class="muted">剧本设计 · 实际游玩</span>
    <span v-if="auth.user" class="muted" style="margin-left:auto">
      {{ auth.user.username }}<template v-if="auth.user.is_admin">（管理员）</template>
      <a href="#" @click.prevent="logout" style="margin-left:10px">登出</a>
    </span>
  </header>
  <main class="wrap">
    <div v-if="!auth.ready" class="muted">加载中…</div>
    <LoginGate v-else-if="!auth.user" />
    <router-view v-else />
  </main>
</template>

<script setup>
import { onMounted } from 'vue'
import { auth, clearSession } from './auth'
import { api } from './api'
import LoginGate from './components/LoginGate.vue'

onMounted(async () => {
  // 有 token 就探测 /me 取用户（含 is_admin）；无效则登出
  if (auth.token) {
    try {
      const me = await api.me()
      auth.user = { username: me.username, is_admin: me.is_admin }
    } catch (_) {
      clearSession()
    }
  }
  auth.ready = true
})

function logout() {
  clearSession()
  location.hash = '#/'
}
</script>
