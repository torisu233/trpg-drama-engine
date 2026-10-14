<template>
  <div>
    <div class="row-between">
      <h2>Feedback · Chat with the admin</h2>
      <router-link to="/" style="align-self:center">← Back</router-link>
    </div>
    <p class="muted">Send questions or suggestions straight to the admin; replies show up here.</p>
    <div class="panel">
      <ChatThread :messages="messages" :mine-is-admin="false" :busy="busy"
                  empty-hint="No messages yet. Send one to get started." @send="send" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { api } from '../api'
import ChatThread from '../components/ChatThread.vue'

const messages = ref([])
const busy = ref(false)
let timer = null

async function load() {
  try { messages.value = (await api.feedbackMine()).messages } catch (_) {}
}
async function send(text) {
  busy.value = true
  try { await api.feedbackSend(text); await load() }
  catch (e) { alert('Send failed: ' + e.message) }
  finally { busy.value = false }
}

onMounted(() => { load(); timer = setInterval(load, 8000) })   // poll for new messages every 8 s while open
onUnmounted(() => clearInterval(timer))
</script>
