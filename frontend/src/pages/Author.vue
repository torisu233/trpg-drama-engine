<template>
  <div>
    <div class="row-between">
      <h2>编剧 · {{ d.id }}</h2>
      <div class="row" style="gap:8px; flex:0 0 auto;">
        <input v-model="saveId" style="width:140px" placeholder="存盘名称" />
        <button @click="save" :disabled="s.busy">保存</button>
        <router-link to="/" style="align-self:center">← 返回</router-link>
      </div>
    </div>

    <div v-if="s.lastMissing.length" class="muted">待补：
      <span class="tag" v-for="m in s.lastMissing" :key="m">{{ m }}</span>
    </div>
    <div v-if="s.lastDone" class="tag" style="color:var(--gold)">✓ 已足够完整，可保存</div>

    <div class="split" style="margin-top:10px">
      <!-- 左：全可编辑面板 -->
      <div>
        <!-- 世界观 -->
        <details class="panel sec" open>
          <summary>世界观</summary>
          <div class="field"><label>基调</label><input v-model="d.世界观.基调" placeholder="如：武侠，江湖恩怨" /></div>
          <div class="field"><label>背景（约 200 字）</label><textarea v-model="d.世界观.背景" rows="3"></textarea></div>
          <div class="field"><label>法则（影响裁决）</label>
            <StrListEditor v-model="d.世界观.法则" ph="一条世界法则" label="添加法则" />
          </div>
        </details>

        <!-- 场景 -->
        <details class="panel sec" open>
          <summary>场景</summary>
          <div class="field"><label>id</label><input v-model="d.scene.id" /></div>
          <div class="field"><label>地点</label><input v-model="d.scene.地点" /></div>
          <div class="field"><label>开场钩子</label><textarea v-model="d.scene.钩子" rows="2"></textarea></div>
          <div class="field"><label>在场角色 id</label>
            <StrListEditor v-model="d.scene.在场" ph="角色 id，如 player" label="加入在场" />
          </div>
        </details>

        <!-- 角色卡 -->
        <details class="panel sec" open>
          <summary>角色卡（{{ Object.keys(d.角色卡).length }}）</summary>
          <div v-for="(c, id) in d.角色卡" :key="id" class="subcard">
            <div class="row-between">
              <strong>{{ c.名 || '(未命名)' }} <span class="muted">[{{ id }}]</span></strong>
              <button class="mini" @click="removeChar(id)">删除角色</button>
            </div>
            <div class="row">
              <div><label>名</label><input v-model="c.名" /></div>
              <div><label>性别</label><input v-model="c.性别" /></div>
            </div>
            <div class="row">
              <div><label>阵营</label>
                <select v-model="c.阵营"><option>我方</option><option>敌</option><option>中立</option></select>
              </div>
              <div><label>扮演</label>
                <select v-model="c.扮演"><option value="玩家">玩家</option><option value="agent">agent</option></select>
              </div>
            </div>
            <label>身分背景（含外貌年龄）</label><textarea v-model="c.身分背景" rows="2"></textarea>
            <label>说话风格</label><input v-model="c.说话风格" />
            <label>动机目标</label><input v-model="c.动机目标" />
            <label>性格</label><StrListEditor v-model="c.性格" label="加" />
            <label>行为偏好</label><StrListEditor v-model="c.行为偏好" label="加" />
            <label>能力</label><StrListEditor v-model="c.能力" label="加" />
            <label>防御特性</label><StrListEditor v-model="c.防御特性" label="加" />
            <label>弱点（可放秘密，配 ledger 的 gm 线索）</label><StrListEditor v-model="c.弱点" label="加" />
          </div>
          <div class="row" style="margin-top:8px">
            <input v-model="newCharId" placeholder="新角色 id（如 aqing）" />
            <button @click="addChar">＋ 添加角色</button>
          </div>
        </details>

        <!-- 初始局面 -->
        <details class="panel sec">
          <summary>初始局面（会变层）</summary>
          <label>场景 · 空间关系</label><CondListEditor v-model="d.会变层.场景.空间关系" />
          <label>场景 · 场景事实（gm 可埋秘密）</label><CondListEditor v-model="d.会变层.场景.场景事实" />
          <label>场景 · 社会事实（债务/承诺/恩怨）</label><CondListEditor v-model="d.会变层.场景.社会事实" />

          <div class="subcard" v-for="(cl, id) in d.会变层.角色" :key="'L'+id">
            <strong class="muted">角色局面 [{{ id }}]</strong>
            <label>姿势位置</label><input v-model="cl.姿势位置" />
            <div class="row">
              <div><label>行动速度</label><input type="number" v-model.number="cl.行动速度" /></div>
              <div><label>感知能力</label><input v-model="cl.感知能力" /></div>
              <div><label>初始行动值（先机）</label><input type="number" v-model.number="cl.行动值" /></div>
            </div>
            <label>身心状况</label><CondListEditor v-model="cl.身心状况" />
            <label>特殊情况（被绑/昏迷等）</label><CondListEditor v-model="cl.特殊情况" />
          </div>
          <div class="row" style="margin-top:8px">
            <select v-model="newLedgerId">
              <option value="">为角色初始化局面…</option>
              <option v-for="id in ledgerCandidates" :key="id" :value="id">{{ id }}</option>
            </select>
            <button @click="addLedger" :disabled="!newLedgerId">＋ 加局面</button>
          </div>
          <div class="muted" style="margin-top:6px">物品、随身、阵营私有等细项可用下方「原始 JSON」编辑。</div>
        </details>

        <!-- 原始 JSON 万用编辑 -->
        <details class="panel sec">
          <summary>高端：原始 JSON（可改任何东西）</summary>
          <button class="mini" @click="loadJson">⤵ 加载目前剧本</button>
          <button class="mini" @click="applyJson">套用 JSON</button>
          <textarea v-model="jsonText" rows="14" style="margin-top:6px; font-size:12px"></textarea>
          <div v-if="jsonErr" class="threat" style="margin-top:6px">{{ jsonErr }}</div>
        </details>
      </div>

      <!-- 右：与编剧对话 -->
      <div>
        <div class="panel" style="display:flex; flex-direction:column; height:560px; position:sticky; top:10px">
          <div class="card-title">与编剧对话</div>
          <div class="chat" ref="chatEl" style="flex:1">
            <div v-if="!s.history.length" class="muted">
              告诉我你想要的剧本：世界、场景、角色…我会边问边填，左侧面板实时更新。<br>
              例：「武侠，落魄镖师在客栈被仇家堵上，有个莽撞的女队友」
            </div>
            <div v-for="(h, i) in s.history" :key="i" :class="h.role === '用户' ? 'me' : 'ai'">
              <strong>{{ h.role }}：</strong>{{ h.text }}
              <span v-if="h.meta && h.meta.区块 && h.meta.区块 !== 'none'" class="tag">
                改了 {{ h.meta.区块 }}{{ h.meta.char_id ? '/' + h.meta.char_id : '' }}
              </span>
            </div>
            <div v-if="s.busy" class="muted">…（编剧思考中）…</div>
          </div>
          <div style="margin-top:8px">
            <textarea v-model="msg" rows="2" placeholder="对编剧说话…（Enter 送出，Shift+Enter 换行）"
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
  d.value.scene.在场.filter((id) => !(id in d.value.会变层.角色)))

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
    名: '', 阵营: '我方', 扮演: 'agent', 性别: '', 身分背景: '', 性格: [],
    说话风格: '', 动机目标: '', 行为偏好: [], 能力: [], 防御特性: [], 弱点: [],
  }
  if (!d.value.scene.在场.includes(id)) d.value.scene.在场.push(id)
  newCharId.value = ''
}
function removeChar(id) {
  delete d.value.角色卡[id]
  d.value.scene.在场 = d.value.scene.在场.filter((x) => x !== id)
  delete d.value.会变层.角色[id]
}
function addLedger() {
  const id = newLedgerId.value
  if (!id || id in d.value.会变层.角色) return
  d.value.会变层.角色[id] = {
    姿势位置: '', 身心状况: [], 特殊情况: [], 物品: {}, 随身: [],
    行动速度: 5, 感知能力: '正常', 行动值: 0,
  }
  newLedgerId.value = ''
}

function loadJson() { jsonText.value = JSON.stringify(d.value, null, 2); jsonErr.value = '' }
function applyJson() {
  try {
    const obj = JSON.parse(jsonText.value)
    s.draft = obj
    jsonErr.value = ''
  } catch (e) { jsonErr.value = 'JSON 解析失败：' + e.message }
}

async function send() {
  const t = msg.value.trim()
  if (!t || s.busy) return
  msg.value = ''
  try { await s.sendMessage(t) } catch (e) { alert('编剧出错：' + e.message) }
}
async function save() {
  const id = (saveId.value || s.draft.id || '未命名').trim()
  try { await s.save(id); alert('已保存：' + id) } catch (e) { alert('保存失败：' + e.message) }
}
</script>
