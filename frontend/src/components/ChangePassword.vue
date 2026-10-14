<template>
  <div class="modal-backdrop" @click.self="$emit('close')">
    <div class="modal panel">
      <div class="row-between">
        <h2 style="margin:0">Change password</h2>
        <button class="mini" @click="$emit('close')">✕</button>
      </div>
      <label>Current password</label>
      <PasswordInput v-model="oldp" autocomplete="current-password" placeholder="Current password" />
      <label>New password (6+ characters)</label>
      <PasswordInput v-model="newp" autocomplete="new-password" placeholder="New password" @enter="submit" />
      <div v-if="err" class="threat" style="margin-top:8px">{{ err }}</div>
      <div v-if="done" class="tag" style="color:var(--gold); margin-top:8px">✓ Password changed</div>
      <button style="margin-top:10px" @click="submit" :disabled="busy || done">{{ busy ? '…' : 'Save' }}</button>
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
  if (!oldp.value || !newp.value) { err.value = 'Enter your current and new password'; return }
  busy.value = true
  err.value = ''
  try {
    await api.changePassword(oldp.value, newp.value)
    done.value = true
    setTimeout(() => emit('close'), 900)
  } catch (e) {
    err.value = e.message || 'Could not change password'
  } finally {
    busy.value = false
  }
}
</script>
