<template>
  <div>
    <div class="row-between">
      <h2>提交反馈 · 与管理员对话</h2>
      <router-link to="/" style="align-self:center">← 返回</router-link>
    </div>
    <p class="muted">有问题或建议直接发给管理员，管理员回复会显示在这里。</p>
    <div class="panel">
      <ChatThread :messages="messages" :mine-is-admin="false" :busy="busy"
                  empty-hint="还没有消息，发一条开始吧。" @send="send" />
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
  catch (e) { alert('发送失败：' + e.message) }
  finally { busy.value = false }
}

onMounted(() => { load(); timer = setInterval(load, 8000) })   // 开着时每 8 秒拉新消息
onUnmounted(() => clearInterval(timer))
</script>
