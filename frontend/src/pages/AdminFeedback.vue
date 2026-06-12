<template>
  <div>
    <div class="row-between">
      <h2>反馈管理</h2>
      <router-link to="/" style="align-self:center">← 返回</router-link>
    </div>

    <div class="fb-split">
      <!-- 左：用户会话列表 -->
      <div class="panel fb-list">
        <div v-if="!threads.length" class="muted">还没有用户反馈。</div>
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

      <!-- 右：选中用户的对话 -->
      <div class="panel fb-chat">
        <div v-if="currentId === null" class="muted" style="padding:8px">← 选一个用户查看对话</div>
        <template v-else>
          <div class="card-title">与 {{ currentName }} 的对话</div>
          <ChatThread :messages="messages" :mine-is-admin="true" :busy="busy"
                      empty-hint="该用户还没有消息。" @send="reply" />
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
  await loadThreads()           // 打开即标已读，刷新未读数
}
async function reply(text) {
  busy.value = true
  try {
    await api.feedbackReply(currentId.value, text)
    await loadThread(currentId.value)
    await loadThreads()
  } catch (e) { alert('回复失败：' + e.message) }
  finally { busy.value = false }
}

async function tick() {
  await loadThreads()
  if (currentId.value !== null) await loadThread(currentId.value)
}

onMounted(() => { loadThreads(); timer = setInterval(tick, 8000) })   // 开着时每 8 秒刷新
onUnmounted(() => clearInterval(timer))
</script>
