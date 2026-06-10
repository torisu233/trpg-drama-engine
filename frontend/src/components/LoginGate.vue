<template>
  <div class="loginwrap">
    <div class="loginbox panel">
      <h2>需要访问密码</h2>
      <p class="muted">请输入主持人提供的密码后进入。</p>
      <input ref="box" v-model="pw" type="password" inputmode="text"
             autocomplete="current-password" placeholder="密码"
             @keyup.enter="submit" />
      <div v-if="err" class="threat" style="margin-top:8px">{{ err }}</div>
      <button style="margin-top:10px" @click="submit" :disabled="busy">
        {{ busy ? '验证中…' : '进入' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { auth, setPw } from '../auth'
import { api } from '../api'

const pw = ref(auth.pw || '')
const err = ref('')
const busy = ref(false)
const box = ref(null)

onMounted(() => box.value && box.value.focus())

async function submit() {
  if (!pw.value) { err.value = '请输入密码'; return }
  busy.value = true
  err.value = ''
  setPw(pw.value)
  try {
    await api.listScenarios()   // 用受保护端点验证密码；成功才放行
    auth.ok = true
  } catch (e) {
    auth.ok = false             // 401 时 api 已清掉密码
    err.value = '密码错误，或服务器无回应。'
  } finally {
    busy.value = false
  }
}
</script>
