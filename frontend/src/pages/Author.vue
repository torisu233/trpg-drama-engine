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
      <!-- 左：全可編輯面板 -->
      <div>
        <!-- 世界觀 -->
        <details class="panel sec" open>
          <summary>世界觀</summary>
          <div class="field"><label>基調</label><input v-model="d.世界觀.基調" placeholder="如：武俠，江湖恩怨" /></div>
          <div class="field"><label>背景（約 200 字）</label><textarea v-model="d.世界觀.背景" rows="3"></textarea></div>
          <div class="field"><label>法則（影響裁決）</label>
            <StrListEditor v-model="d.世界觀.法則" ph="一條世界法則" label="新增法則" />
          </div>
        </details>

        <!-- 場景 -->
        <details class="panel sec" open>
          <summary>場景</summary>
          <div class="field"><label>id</label><input v-model="d.scene.id" /></div>
          <div class="field"><label>地點</label><input v-model="d.scene.地點" /></div>
          <div class="field"><label>開場鉤子</label><textarea v-model="d.scene.鉤子" rows="2"></textarea></div>
          <div class="field"><label>在場角色 id</label>
            <StrListEditor v-model="d.scene.在場" ph="角色 id，如 player" label="加入在場" />
          </div>
        </details>

        <!-- 角色卡 -->
        <details class="panel sec" open>
          <summary>角色卡（{{ Object.keys(d.角色卡).length }}）</summary>
          <div v-for="(c, id) in d.角色卡" :key="id" class="subcard">
            <div class="row-between">
              <strong>{{ c.名 || '(未命名)' }} <span class="muted">[{{ id }}]</span></strong>
              <button class="mini" @click="removeChar(id)">刪除角色</button>
            </div>
            <div class="row">
              <div><label>名</label><input v-model="c.名" /></div>
              <div><label>性別</label><input v-model="c.性別" /></div>
            </div>
            <div class="row">
              <div><label>陣營</label>
                <select v-model="c.陣營"><option>我方</option><option>敵</option><option>中立</option></select>
              </div>
              <div><label>扮演</label>
                <select v-model="c.扮演"><option value="玩家">玩家</option><option value="agent">agent</option></select>
              </div>
            </div>
            <label>身分背景（含外貌年齡）</label><textarea v-model="c.身分背景" rows="2"></textarea>
            <label>說話風格</label><input v-model="c.說話風格" />
            <label>動機目標</label><input v-model="c.動機目標" />
            <label>性格</label><StrListEditor v-model="c.性格" label="加" />
            <label>行為偏好</label><StrListEditor v-model="c.行為偏好" label="加" />
            <label>能力</label><StrListEditor v-model="c.能力" label="加" />
            <label>防禦特性</label><StrListEditor v-model="c.防禦特性" label="加" />
            <label>弱點（可放秘密，配 ledger 的 gm 線索）</label><StrListEditor v-model="c.弱點" label="加" />
          </div>
          <div class="row" style="margin-top:8px">
            <input v-model="newCharId" placeholder="新角色 id（如 aqing）" />
            <button @click="addChar">＋ 新增角色</button>
          </div>
        </details>

        <!-- 初始局面 -->
        <details class="panel sec">
          <summary>初始局面（會變層）</summary>
          <label>場景 · 空間關係</label><CondListEditor v-model="d.會變層.場景.空間關係" />
          <label>場景 · 場景事實（gm 可埋秘密）</label><CondListEditor v-model="d.會變層.場景.場景事實" />
          <label>場景 · 社會事實（債務/承諾/恩怨）</label><CondListEditor v-model="d.會變層.場景.社會事實" />

          <div class="subcard" v-for="(cl, id) in d.會變層.角色" :key="'L'+id">
            <strong class="muted">角色局面 [{{ id }}]</strong>
            <label>姿勢位置</label><input v-model="cl.姿勢位置" />
            <div class="row">
              <div><label>行動速度</label><input type="number" v-model.number="cl.行動速度" /></div>
              <div><label>感知能力</label><input v-model="cl.感知能力" /></div>
              <div><label>初始行動值（先機）</label><input type="number" v-model.number="cl.行動值" /></div>
            </div>
            <label>身心狀況</label><CondListEditor v-model="cl.身心狀況" />
            <label>特殊情況（被綁/昏迷等）</label><CondListEditor v-model="cl.特殊情況" />
          </div>
          <div class="row" style="margin-top:8px">
            <select v-model="newLedgerId">
              <option value="">為角色初始化局面…</option>
              <option v-for="id in ledgerCandidates" :key="id" :value="id">{{ id }}</option>
            </select>
            <button @click="addLedger" :disabled="!newLedgerId">＋ 加局面</button>
          </div>
          <div class="muted" style="margin-top:6px">物品、隨身、陣營私有等細項可用下方「原始 JSON」編輯。</div>
        </details>

        <!-- 原始 JSON 萬用編輯 -->
        <details class="panel sec">
          <summary>進階：原始 JSON（可改任何東西）</summary>
          <button class="mini" @click="loadJson">⤵ 載入目前劇本</button>
          <button class="mini" @click="applyJson">套用 JSON</button>
          <textarea v-model="jsonText" rows="14" style="margin-top:6px; font-size:12px"></textarea>
          <div v-if="jsonErr" class="threat" style="margin-top:6px">{{ jsonErr }}</div>
        </details>
      </div>

      <!-- 右：與編劇對話 -->
      <div>
        <div class="panel" style="display:flex; flex-direction:column; height:560px; position:sticky; top:10px">
          <div class="card-title">與編劇對話</div>
          <div class="chat" ref="chatEl" style="flex:1">
            <div v-if="!s.history.length" class="muted">
              告訴我你想要的劇本：世界、場景、角色…我會邊問邊填，左側面板即時更新。<br>
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
import StrListEditor from '../components/StrListEditor.vue'
import CondListEditor from '../components/CondListEditor.vue'

const s = useScenarioStore()
const route = useRoute()
const d = computed(() => s.draft)
const msg = ref('')
const saveId = ref('')
const chatEl = ref(null)
const newCharId = ref('')
const newLedgerId = ref('')
const jsonText = ref('')
const jsonErr = ref('')

const ledgerCandidates = computed(() =>
  d.value.scene.在場.filter((id) => !(id in d.value.會變層.角色)))

onMounted(async () => {
  const id = route.params.id
  if (id) await s.loadDraft(id)
  saveId.value = s.draft.id && s.draft.id !== '未命名' ? s.draft.id : ''
})

watch(() => s.history.length, () => nextTick(() => {
  if (chatEl.value) chatEl.value.scrollTop = chatEl.value.scrollHeight
}))

function addChar() {
  const id = newCharId.value.trim()
  if (!id || id in d.value.角色卡) return
  d.value.角色卡[id] = {
    名: '', 陣營: '我方', 扮演: 'agent', 性別: '', 身分背景: '', 性格: [],
    說話風格: '', 動機目標: '', 行為偏好: [], 能力: [], 防禦特性: [], 弱點: [],
  }
  if (!d.value.scene.在場.includes(id)) d.value.scene.在場.push(id)
  newCharId.value = ''
}
function removeChar(id) {
  delete d.value.角色卡[id]
  d.value.scene.在場 = d.value.scene.在場.filter((x) => x !== id)
  delete d.value.會變層.角色[id]
}
function addLedger() {
  const id = newLedgerId.value
  if (!id || id in d.value.會變層.角色) return
  d.value.會變層.角色[id] = {
    姿勢位置: '', 身心狀況: [], 特殊情況: [], 物品: {}, 隨身: [],
    行動速度: 5, 感知能力: '正常', 行動值: 0,
  }
  newLedgerId.value = ''
}

function loadJson() { jsonText.value = JSON.stringify(d.value, null, 2); jsonErr.value = '' }
function applyJson() {
  try {
    const obj = JSON.parse(jsonText.value)
    s.draft = obj
    jsonErr.value = ''
  } catch (e) { jsonErr.value = 'JSON 解析失敗：' + e.message }
}

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
