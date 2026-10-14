<template>
  <div class="chatthread">
    <div class="chatbox" ref="boxEl">
      <div v-if="!messages.length" class="muted" style="padding:8px">{{ emptyHint }}</div>
      <div v-for="m in messages" :key="m.id"
           class="msg" :class="(m.sender_is_admin === mineIsAdmin) ? 'mine' : 'other'">
        <div class="bubble">{{ m.body }}</div>
        <div class="msg-meta">{{ m.sender_is_admin ? 'Admin' : 'User' }} · {{ fmt(m.created_at) }}</div>
      </div>
    </div>
    <div class="chatinput" v-if="!readonly">
      <textarea v-model="draft" rows="2" :placeholder="placeholder"
                @keydown.enter.exact.prevent="send"></textarea>
      <button @click="send" :disabled="busy || !draft.trim()">Send</button>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, onMounted } from 'vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  mineIsAdmin: { type: Boolean, default: false },   // whether the current viewer is admin (decides which side is "me")
  busy: { type: Boolean, default: false },
  placeholder: { type: String, default: 'Type a message… (Enter to send, Shift+Enter for a new line)' },
  emptyHint: { type: String, default: 'No messages yet.' },
  readonly: { type: Boolean, default: false },
})
const emit = defineEmits(['send'])

const draft = ref('')
const boxEl = ref(null)

function fmt(iso) {
  try { return new Date(iso).toLocaleString() } catch (_) { return '' }
}
function send() {
  const t = draft.value.trim()
  if (!t || props.busy) return
  emit('send', t)
  draft.value = ''
}
function scrollDown() {
  nextTick(() => { if (boxEl.value) boxEl.value.scrollTop = boxEl.value.scrollHeight })
}
onMounted(scrollDown)
watch(() => props.messages.length, scrollDown)
</script>
