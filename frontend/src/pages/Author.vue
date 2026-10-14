<template>
  <div>
    <div class="row-between">
      <h2>编剧 · {{ d.id }}</h2>
      <div class="row" style="gap:8px; flex:0 0 auto;">
        <input v-model="d.id" style="width:140px" placeholder="剧本名称" />
        <select v-model="s.visibility" style="width:88px">
          <option value="private">私人</option>
          <option value="published">发布</option>
        </select>
        <button @click="save" :disabled="s.busy">保存</button>
        <router-link to="/" class="back-btn">← 返回</router-link>
      </div>
    </div>

    <div v-if="s.lastMissing.length" class="muted">待补：
      <span class="tag" v-for="m in s.lastMissing" :key="m">{{ m }}</span>
    </div>
    <div v-if="s.lastDone" class="tag" style="color:var(--gold)">✓ 已足够完整，可保存</div>

    <div class="split" style="margin-top:10px">
      <!-- 左：全可编辑面板 -->
      <div>
        <!-- world -->
        <details class="panel sec" open>
          <summary>world</summary>
          <div class="field"><label>tone</label><input v-model="d.world.tone" placeholder="如：武侠，江湖恩怨" /></div>
          <div class="field"><label>background（约 200 字）</label><textarea v-model="d.world.background" rows="3"></textarea></div>
          <div class="field"><label>laws（影响裁决·人人皆知）</label>
            <div class="hint muted small">laws=这个世界的公共规则，裁决与所有角色都看得到；勿写任何一方的秘密。秘密请用角色「weaknesses」或会变层里 gm 可见性的场景事实。</div>
            <StrListEditor v-model="d.world.laws" ph="一条世界法则" label="添加法则" />
          </div>
        </details>

        <!-- scene -->
        <details class="panel sec" open>
          <summary>scene</summary>
          <div class="field"><label>id</label><input v-model="d.scene.id" /></div>
          <div class="field"><label>location</label><input v-model="d.scene.location" /></div>
          <div class="field"><label>开场钩子</label><textarea v-model="d.scene.hook" rows="2"></textarea></div>
          <div class="field"><label>在场角色 id</label>
            <StrListEditor v-model="d.scene.present" ph="characters id，如 player" label="加入在场" />
          </div>
        </details>

        <!-- cards -->
        <details class="panel sec" open>
          <summary>cards（{{ Object.keys(d.cards).length }}）</summary>
          <div v-for="(c, id) in d.cards" :key="id" class="subcard">
            <div class="row-between">
              <strong>{{ c.name || '(未命名)' }} <span class="muted">[{{ id }}]</span></strong>
              <button class="mini" @click="removeChar(id)">删除角色</button>
            </div>
            <div class="row">
              <div><label>name</label><input v-model="c.name" /></div>
              <div><label>gender</label><input v-model="c.gender" /></div>
            </div>
            <div class="row">
              <div><label>faction</label>
                <select v-model="c.faction"><option>ally</option><option>enemy</option><option>neutral</option></select>
              </div>
              <div><label>controller</label>
                <select v-model="c.controller"><option value="player">player</option><option value="agent">agent</option></select>
              </div>
            </div>
            <label>backstory（含外貌年龄）</label><textarea v-model="c.backstory" rows="2"></textarea>
            <label>directive（保底·最高优先，只喂角色 AI）</label>
            <textarea v-model="c.directive" rows="2"
              placeholder="只填 1–3 条必须不折不扣遵守的核心铁律（如「绝不背叛玩家」「坚信自己是真命天子」）；日常性格/口吻请用下面的结构化字段，堆太多角色会变木。仅压人设、不越游戏规则。"></textarea>
            <label>voice</label><input v-model="c.voice" />
            <label>motive</label><input v-model="c.motive" />
            <label>personality</label><StrListEditor v-model="c.personality" label="加" />
            <label>tactics</label><StrListEditor v-model="c.tactics" label="加" />
            <label>abilities</label><StrListEditor v-model="c.abilities" label="加" />
            <label>defenses</label><StrListEditor v-model="c.defenses" label="加" />
            <label>weaknesses（可放秘密，配 ledger 的 gm 线索）</label><StrListEditor v-model="c.weaknesses" label="加" />
          </div>
          <div class="row" style="margin-top:8px">
            <input v-model="newCharId" placeholder="新角色 id（如 aqing）" />
            <button @click="addChar">＋ 添加角色</button>
          </div>
        </details>

        <!-- 初始局面 -->
        <details class="panel sec">
          <summary>初始局面（ledger）</summary>
          <label>scene · spatial</label><CondListEditor v-model="d.ledger.scene.spatial" />
          <label>scene · scene_facts（gm 可埋秘密）</label><CondListEditor v-model="d.ledger.scene.scene_facts" />
          <label>scene · social_facts（债务/承诺/恩怨）</label><CondListEditor v-model="d.ledger.scene.social_facts" />

          <div class="subcard" v-for="(cl, id) in d.ledger.characters" :key="'L'+id">
            <strong class="muted">角色局面 [{{ id }}]</strong>
            <label>posture</label><input v-model="cl.posture" />
            <div class="row">
              <div><label>speed</label><input type="number" v-model.number="cl.speed" /></div>
              <div><label>perception</label><input v-model="cl.perception" /></div>
              <div><label>初始行动值（先机）</label><input type="number" v-model.number="cl.gauge" /></div>
            </div>
            <label>conditions</label><CondListEditor v-model="cl.conditions" />
            <label>status_effects（被绑/昏迷等）</label><CondListEditor v-model="cl.status_effects" />
          </div>
          <div class="row" style="margin-top:8px">
            <select v-model="newLedgerId">
              <option value="">为角色初始化局面…</option>
              <option v-for="id in ledgerCandidates" :key="id" :value="id">{{ id }}</option>
            </select>
            <button @click="addLedger" :disabled="!newLedgerId">＋ 加局面</button>
          </div>
          <div class="muted" style="margin-top:6px">items、carried、阵营私有等细项可用下方「原始 JSON」编辑。</div>
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
              告诉我你想要的剧本：世界、scene、characters…我会边问边填，左侧面板实时更新。<br>
              例：「武侠，落魄镖师在客栈被仇家堵上，有个莽撞的女队友」
            </div>
            <div v-for="(h, i) in s.history" :key="i" :class="h.role === '用户' ? 'me' : 'ai'">
              <strong>{{ h.role }}：</strong>{{ h.text }}
              <span v-if="h.meta && h.meta.block && h.meta.block !== 'none'" class="tag">
                改了 {{ h.meta.block }}{{ h.meta.char_id ? '/' + h.meta.char_id : '' }}
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
import { useRoute, useRouter } from 'vue-router'
import { useScenarioStore } from '../stores/scenario'
import StrListEditor from '../components/StrListEditor.vue'
import CondListEditor from '../components/CondListEditor.vue'

const s = useScenarioStore()
const route = useRoute()
const router = useRouter()
const d = computed(() => s.draft)
const msg = ref('')
const chatEl = ref(null)
const newCharId = ref('')
const newLedgerId = ref('')
const jsonText = ref('')
const jsonErr = ref('')

const ledgerCandidates = computed(() =>
  d.value.scene.present.filter((id) => !(id in d.value.ledger.characters)))

onMounted(async () => {
  const id = route.params.id
  if (id) {
    try { await s.loadDraft(id) } catch (e) { alert('加载失败：' + e.message); router.push('/') }
  }
})

watch(() => s.history.length, () => nextTick(() => {
  if (chatEl.value) chatEl.value.scrollTop = chatEl.value.scrollHeight
}))

function addChar() {
  const id = newCharId.value.trim()
  if (!id || id in d.value.cards) return
  d.value.cards[id] = {
    name: '', faction: 'ally', controller: 'agent', gender: '', backstory: '', directive: '', personality: [],
    voice: '', motive: '', tactics: [], abilities: [], defenses: [], weaknesses: [],
  }
  if (!d.value.scene.present.includes(id)) d.value.scene.present.push(id)
  newCharId.value = ''
}
function removeChar(id) {
  delete d.value.cards[id]
  d.value.scene.present = d.value.scene.present.filter((x) => x !== id)
  delete d.value.ledger.characters[id]
}
function addLedger() {
  const id = newLedgerId.value
  if (!id || id in d.value.ledger.characters) return
  d.value.ledger.characters[id] = {
    posture: '', conditions: [], status_effects: [], items: {}, carried: [],
    speed: 5, perception: 'normal', gauge: 0,
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
  if (!d.value.id || !d.value.id.trim()) { alert('请先填剧本名称'); return }
  try {
    const wasNew = !s.currentId
    const id = await s.save()
    if (wasNew) router.push('/author/' + id)   // 新建后带上 id，后续是更新
    alert('已保存')
  } catch (e) { alert('保存失败：' + e.message) }
}
</script>

<style scoped>
/* 「返回」描边按钮：与「保存」（实心 button）等高同风，用项目设计变量 --line/--gold */
.back-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 7px 13px;                 /* = button 的 8px14px 减去 1px 边框 → 等高 */
  font-size: 14px;
  background: transparent;
  color: var(--ink);
  border: 1px solid var(--line);
  border-radius: 6px;
  text-decoration: none;
  white-space: nowrap;
}
.back-btn:hover { color: var(--gold); border-color: var(--gold); }
</style>
