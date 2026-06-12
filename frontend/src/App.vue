<template>
  <header class="topbar">
    <router-link class="brand" to="/">🎭 跑团工作室</router-link>
    <span class="muted">剧本设计 · 实际游玩</span>

    <div v-if="auth.user" class="usermenu" style="margin-left:auto">
      <button class="userbtn" @click="menuOpen = !menuOpen">
        {{ auth.user.username }}<span v-if="auth.user.is_admin" class="muted">（管理员）</span> ▾
      </button>
      <template v-if="menuOpen">
        <div class="menu-backdrop" @click="menuOpen = false"></div>
        <div class="menu">
          <a href="#" @click.prevent="openPw">修改密码</a>
          <router-link v-if="auth.user.is_admin" to="/admin/feedback" @click="menuOpen = false">查看反馈</router-link>
          <router-link v-else to="/feedback" @click="menuOpen = false">提交反馈</router-link>
          <a href="#" @click.prevent="logout">登出</a>
        </div>
      </template>
    </div>
  </header>

  <main class="wrap">
    <div v-if="!auth.ready" class="muted">加载中…</div>
    <LoginGate v-else-if="!auth.user" />
    <router-view v-else />
  </main>

  <ChangePassword v-if="pwOpen" @close="pwOpen = false" />
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { auth, clearSession } from './auth'
import { api } from './api'
import LoginGate from './components/LoginGate.vue'
import ChangePassword from './components/ChangePassword.vue'

const menuOpen = ref(false)
const pwOpen = ref(false)

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

function openPw() { menuOpen.value = false; pwOpen.value = true }
function logout() {
  menuOpen.value = false
  clearSession()
  location.hash = '#/'
}
</script>
