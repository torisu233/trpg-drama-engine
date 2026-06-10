<template>
  <div>
    <div class="row-between">
      <h2>編劇 · {{ d.id }}</h2>
      <div class="row" style="gap:8px; flex:0 0 auto;">
        <input v-model="saveId" style="width:140px" placeholder="存檔名稱" />
        <button @click="save" :disabled="s.busy">儲存</button>
        <router-link to="/" style="align-self:center">← 返回</router-link>
      </div>
    </div>

    <div v-if="s.lastMissing.length" class="muted">待補：
      <span class="tag" v-for="m in s.lastMissing" :key="m">{{ m }}</span>
    </div>
    <div v-if="s.lastDone" class="tag" style="color:var(--gold)">✓ 已足夠完整，可儲存</div>

    <div class="split" style="margin-top:10px">
      <!-- 左：劇本面板（可手動編輯關鍵欄；其餘靠對話） -->
      <div>
        <div class="panel">
          <div class="card-title">世界觀</div>
          <label>基調</label>
          <input v-model="d.世界觀.基調" placeholder="如：武俠，江湖恩怨" />
          <label>背景（約 200 字）</label>
          <textarea v-model="d.世界觀.背景" rows="3"></textarea>
          <label>法則（影響裁決）</label>
          <div v-if="d.世界觀.法則.length">
            <div v-for="(f, i) in d.世界觀.法則" :key="i" class="muted">· {{ f }}</div>
          </div>
          <div v-else class="muted">（尚無，可請編劇補）</div>
        </div>

        <div class="panel">
          <div class="card-title">場景</div>
          <label>地點</label>
          <input v-model="d.scene.地點" />
          <label>開場鉤子</label>
          <textarea v-model="d.scene.鉤子" rows="2"></textarea>
          <div class="muted" style="margin-top:6px">在場：
            <span class="tag" v-for="id in d.scene.在場" :key="id">{{ id }}</span>
            <span v-if="!d.scene.在場.length">（尚無）</span>
          </div>
        </div>

        <div class="panel">
          <div class="card-title">角色卡（{{ Object.keys(d.角色卡).length }}）</div>
          <div v-for="(c, id) in d.角色卡" :key="id" style="border-top:1px dashed var(--line); padding:6px 0">
            <strong>{{ c.名 }}</strong>
            <span class="muted"> [{{ id }}] {{ c.陣營 }}/{{ c.性別 || '?' }} · {{ c.扮演 }}</span>
            <div class="muted">能力：{{ (c.能力 || []).join('、') || '—' }}</div>
            <div class="muted">弱點：{{ (c.弱點 || []).join('、') || '—' }}</div>
          </div>
          <div v-if="!Object.keys(d.角色卡).length" class="muted">（尚無角色，請在對話框要求建立）</div>
        </div>

        <div class="panel">
          <div class="card-title">初始局面</div>
          <div class="muted">已配置角色 {{ Object.keys(d.會變層.角色).length }}｜空間關係
            {{ d.會變層.場景.空間關係.length }}｜場景事實 {{ d.會變層.場景.場景事實.length }}｜社會事實
            {{ d.會變層.場景.社會事實.length }}</div>
        </div>

        <details><summary class="muted">原始 JSON</summary><pre>{{ JSON.stringify(d, null, 2) }}</pre></details>
      </div>

      <!-- 右：與編劇對話 -->
      <div>
        <div class="panel" style="display:flex; flex-direction:column; height:520px">
          <div class="card-title">與編劇對話</div>
          <div class="chat" ref="chatEl" style="flex:1">
            <div v-if="!s.history.length" class="muted">
              告訴我你想要的劇本：世界、場景、角色…我會邊問邊填。<br>
              例：「武俠，落魄鏢師在客棧被仇家堵上，有個莽撞的女隊友」
            </div>
            <div v-for="(h, i) in s.history" :key="i" :class="h.role === '使用者' ? 'me' : 'ai'">
              <strong>{{ h.role }}：</strong>{{ h.text }}
              <span v-if="h.meta && h.meta.區塊 && h.meta.區塊 !== 'none'" class="tag">
                改了 {{ h.meta.區塊 }}{{ h.meta.char_id ? '/' + h.meta.char_id : '' }}
              </span>
            </div>
            <div v-if="s.busy" class="muted">…（編劇思考中）…</div>
          </div>
          <div style="margin-top:8px">
            <textarea v-model="msg" rows="2" placeholder="對編劇說話…（Enter 送出，Shift+Enter 換行）"
              @keydown.enter.exact.prevent="send"></textarea>
            <button style="margin-top:6px" @click="send" :disabled="s.busy || !msg.trim()">送出</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useScenarioStore } from '../stores/scenario'

const s = useScenarioStore()
const route = useRoute()
const d = computed(() => s.draft)
const msg = ref('')
const saveId = ref('')
const chatEl = ref(null)

onMounted(async () => {
  const id = route.params.id
  if (id) await s.loadDraft(id)
  saveId.value = s.draft.id && s.draft.id !== '未命名' ? s.draft.id : ''
})

watch(() => s.history.length, () => nextTick(() => {
  if (chatEl.value) chatEl.value.scrollTop = chatEl.value.scrollHeight
}))

async function send() {
  const t = msg.value.trim()
  if (!t || s.busy) return
  msg.value = ''
  try { await s.sendMessage(t) } catch (e) { alert('編劇出錯：' + e.message) }
}

async function save() {
  const id = (saveId.value || s.draft.id || '未命名').trim()
  try { await s.save(id); alert('已儲存：' + id) } catch (e) { alert('儲存失敗：' + e.message) }
}
</script>
