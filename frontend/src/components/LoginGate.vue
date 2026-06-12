<template>
  <div class="loginwrap">
    <div class="loginbox panel">
      <h2>{{ mode === 'login' ? '登录' : '注册' }}</h2>
      <p class="muted">{{ mode === 'login' ? '输入账号密码进入。' : '自己填账号和密码即可注册。' }}</p>
      <input v-model="username" placeholder="账号（3–32 位）" autocomplete="username" @keyup.enter="submit" />
      <PasswordInput v-model="password" placeholder="密码（≥6 位）"
                     :autocomplete="mode === 'login' ? 'current-password' : 'new-password'" @enter="submit" />
      <div v-if="err" class="threat" style="margin-top:8px">{{ err }}</div>
      <button style="margin-top:10px" @click="submit" :disabled="busy">
        {{ busy ? '…' : (mode === 'login' ? '登录' : '注册') }}
      </button>
      <div class="muted" style="margin-top:10px; cursor:pointer" @click="toggle">
        {{ mode === 'login' ? '没有账号？去注册' : '已有账号？去登录' }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { auth, setSession } from '../auth'
import { api } from '../api'
import PasswordInput from './PasswordInput.vue'

const mode = ref('login')
const username = ref('')
const password = ref('')
const err = ref('')
const busy = ref(false)

function toggle() { mode.value = mode.value === 'login' ? 'register' : 'login'; err.value = '' }

async function submit() {
  if (!username.value.trim() || !password.value) { err.value = '请输入账号和密码'; return }
  busy.value = true
  err.value = ''
  try {
    const call = mode.value === 'login' ? api.login : api.register
    const r = await call(username.value.trim(), password.value)
    setSession(r.token, { username: r.username, is_admin: r.is_admin })
    auth.ready = true
  } catch (e) {
    err.value = e.message || '失败'
  } finally {
    busy.value = false
  }
}
</script>
