<template>
  <div class="modal-backdrop" @click.self="$emit('close')">
    <div class="modal panel">
      <div class="row-between">
        <h2 style="margin:0">修改密码</h2>
        <button class="mini" @click="$emit('close')">✕</button>
      </div>
      <label>原密码</label>
      <PasswordInput v-model="oldp" autocomplete="current-password" placeholder="原密码" />
      <label>新密码（≥6 位）</label>
      <PasswordInput v-model="newp" autocomplete="new-password" placeholder="新密码" @enter="submit" />
      <div v-if="err" class="threat" style="margin-top:8px">{{ err }}</div>
      <div v-if="done" class="tag" style="color:var(--gold); margin-top:8px">✓ 已修改</div>
      <button style="margin-top:10px" @click="submit" :disabled="busy || done">{{ busy ? '…' : '保存' }}</button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { api } from '../api'
import PasswordInput from './PasswordInput.vue'

const emit = defineEmits(['close'])
const oldp = ref('')
const newp = ref('')
const err = ref('')
const done = ref(false)
const busy = ref(false)

async function submit() {
  if (!oldp.value || !newp.value) { err.value = '请填原密码和新密码'; return }
  busy.value = true
  err.value = ''
  try {
    await api.changePassword(oldp.value, newp.value)
    done.value = true
    setTimeout(() => emit('close'), 900)
  } catch (e) {
    err.value = e.message || '修改失败'
  } finally {
    busy.value = false
  }
}
</script>
