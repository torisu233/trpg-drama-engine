<template>
  <div>
    <div class="row-between">
      <h2>Feedback inbox</h2>
      <router-link to="/" style="align-self:center">← Back</router-link>
    </div>

    <div class="fb-split">
      <!-- Left: user thread list -->
      <div class="panel fb-list">
        <div v-if="!threads.length" class="muted">No user feedback yet.</div>
        <div v-for="t in threads" :key="t.user_id"
             class="fb-item" :class="{ active: t.user_id === currentId }"
             @click="open(t.user_id)">
          <div class="row-between">
            <strong>{{ t.username }}</strong>
            <span v-if="t.unread" class="fb-badge">{{ t.unread }}</span>
          </div>
          <div class="muted fb-last">{{ t.last }}</div>
        </div>
      </div>

      <!-- Right: conversation with the selected user -->
      <div class="panel fb-chat">
        <div v-if="currentId === null" class="muted" style="padding:8px">← Pick a user to view the conversation</div>
        <template v-else>
          <div class="card-title">Conversation with {{ currentName }}</div>
          <ChatThread :messages="messages" :mine-is-admin="true" :busy="busy"
                      empty-hint="This user has no messages yet." @send="reply" />
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { api } from '../api'
import ChatThread from '../components/ChatThread.vue'

const threads = ref([])
const currentId = ref(null)
const currentName = ref('')
const messages = ref([])
const busy = ref(false)
let timer = null

async function loadThreads() {
  try { threads.value = (await api.feedbackThreads()).threads } catch (_) {}
}
async function loadThread(uid) {
  try {
    const r = await api.feedbackThread(uid)
    messages.value = r.messages
    currentName.value = r.username
  } catch (_) {}
}
async function open(uid) {
  currentId.value = uid
  await loadThread(uid)
  await loadThreads()           // opening marks it read; refresh unread counts
}
async function reply(text) {
  busy.value = true
  try {
    await api.feedbackReply(currentId.value, text)
    await loadThread(currentId.value)
    await loadThreads()
  } catch (e) { alert('Reply failed: ' + e.message) }
  finally { busy.value = false }
}

async function tick() {
  await loadThreads()
  if (currentId.value !== null) await loadThread(currentId.value)
}

onMounted(() => { loadThreads(); timer = setInterval(tick, 8000) })   // refresh every 8 s while open
onUnmounted(() => clearInterval(timer))
</script>
