<template>
  <header class="topbar">
    <router-link class="brand" to="/">🎭 TRPG Drama Engine</router-link>
    <span class="muted">Write scenarios · Play them</span>

    <div v-if="auth.user" class="usermenu" style="margin-left:auto">
      <button class="userbtn" @click="menuOpen = !menuOpen">
        {{ auth.user.username }}<span v-if="auth.user.is_admin" class="muted"> (admin)</span> ▾
      </button>
      <template v-if="menuOpen">
        <div class="menu-backdrop" @click="menuOpen = false"></div>
        <div class="menu">
          <a href="#" @click.prevent="openPw">Change password</a>
          <router-link v-if="auth.user.is_admin" to="/admin/feedback" @click="menuOpen = false">View feedback</router-link>
          <router-link v-else to="/feedback" @click="menuOpen = false">Send feedback</router-link>
          <a href="#" @click.prevent="logout">Sign out</a>
        </div>
      </template>
    </div>
  </header>

  <main class="wrap">
    <div v-if="!auth.ready" class="muted">Loading…</div>
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
  // If we have a token, probe /me for the user (incl. is_admin); sign out if it is invalid
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
