<template>
  <div class="loginwrap">
    <div class="loginbox panel">
      <h2>{{ mode === 'login' ? 'Sign in' : 'Register' }}</h2>
      <p class="muted">{{ mode === 'login' ? 'Enter your username and password.' : 'Pick a username and password to register.' }}</p>
      <input v-model="username" placeholder="Username (3–32 characters)" autocomplete="username" @keyup.enter="submit" />
      <PasswordInput v-model="password" placeholder="Password (6+ characters)"
                     :autocomplete="mode === 'login' ? 'current-password' : 'new-password'" @enter="submit" />
      <div v-if="err" class="threat" style="margin-top:8px">{{ err }}</div>
      <button style="margin-top:10px" @click="submit" :disabled="busy">
        {{ busy ? '…' : (mode === 'login' ? 'Sign in' : 'Register') }}
      </button>
      <div class="muted" style="margin-top:10px; cursor:pointer" @click="toggle">
        {{ mode === 'login' ? 'No account? Register' : 'Have an account? Sign in' }}
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
  if (!username.value.trim() || !password.value) { err.value = 'Enter a username and password'; return }
  busy.value = true
  err.value = ''
  try {
    const call = mode.value === 'login' ? api.login : api.register
    const r = await call(username.value.trim(), password.value)
    setSession(r.token, { username: r.username, is_admin: r.is_admin })
    auth.ready = true
  } catch (e) {
    err.value = e.message || 'Failed'
  } finally {
    busy.value = false
  }
}
</script>
