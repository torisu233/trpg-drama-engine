<template>
  <header class="topbar">
    <router-link class="brand" to="/">🎭 跑团工作室</router-link>
    <span class="muted">剧本设计 · 实际游玩</span>
  </header>
  <main class="wrap">
    <div v-if="!ready" class="muted">加载中…</div>
    <LoginGate v-else-if="!auth.ok" />
    <router-view v-else />
  </main>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { auth } from './auth'
import { api } from './api'
import LoginGate from './components/LoginGate.vue'

const ready = ref(false)

onMounted(async () => {
  // 探测一次：服务器无密码→直接进；已存正确密码→直接进；否则(401)显示登录闸
  try { await api.listScenarios(); auth.ok = true } catch { auth.ok = false }
  ready.value = true
})
</script>
