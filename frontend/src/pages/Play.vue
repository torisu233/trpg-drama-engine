<template>
  <div>
    <div class="row-between">
      <h2>游玩</h2>
      <router-link to="/">← 返回剧本集</router-link>
    </div>

    <div v-if="!snap" class="muted">加载中…</div>
    <template v-else>
      <!-- 你的局面（常驻置顶）-->
      <div class="panel situ" v-if="snap.situation">
        <div class="situ-line"><b>scene</b>{{ snap.situation.scene }}</div>
        <div class="situ-line" v-if="snap.situation.surroundings && snap.situation.surroundings.length"><b>surroundings</b>{{ snap.situation.surroundings.join('；') }}</div>
        <div class="situ-line" v-if="snap.situation.intel && snap.situation.intel.length"><b>约定/intel</b>{{ snap.situation.intel.join('；') }}</div>
        <div class="situ-line muted" v-if="snap.situation.plans && snap.situation.plans.length"><b>我方计策</b>{{ snap.situation.plans.join('；') }}</div>
      </div>

      <!-- 在场角色：我方详尽 / 敌方仅可见 -->
      <div class="cards rolecards" v-if="snap.characters && snap.characters.length">
        <div v-for="c in snap.characters" :key="c.id" class="card role" :class="roleClass(c)">
          <div class="card-title">
            {{ c.name }}
            <span class="muted small">· {{ c.faction }}<template v-if="c.gender">·{{ c.gender }}</template><template v-if="c.is_self">·你</template></span>
          </div>
          <div class="small muted">速度 {{ c.speed }} · 感知 {{ c.perception }}</div>
          <div class="small">{{ c.posture || 'present' }}</div>
          <div class="small" v-if="c.state && c.state.length">state：{{ c.state.join('，') }}</div>
          <template v-if="c.is_ally">
            <div class="small" v-if="c.abilities && c.abilities.length"><b>abilities</b> {{ c.abilities.join('、') }}</div>
            <div class="small" v-if="c.defenses && c.defenses.length"><b>防御</b> {{ c.defenses.join('、') }}</div>
            <div class="small weak" v-if="c.weaknesses && c.weaknesses.length"><b>weaknesses</b> {{ c.weaknesses.join('、') }}</div>
            <div class="small muted" v-if="c.motive"><b>动机</b> {{ c.motive }}</div>
            <details v-if="hasMore(c)" class="more">
              <summary class="muted small">更多</summary>
              <div class="small" v-if="c.backstory">身份：{{ c.backstory }}</div>
              <div class="small" v-if="c.personality && c.personality.length">personality：{{ c.personality.join('、') }}</div>
              <div class="small" v-if="c.voice">说话：{{ c.voice }}</div>
              <div class="small" v-if="c.tactics && c.tactics.length">偏好：{{ c.tactics.join('、') }}</div>
              <div class="small" v-if="c.inventory && c.inventory.length">inventory：{{ c.inventory.join('、') }}</div>
            </details>
          </template>
          <div class="small muted foe-hint" v-else>底细未知，靠观察判断</div>
        </div>
      </div>

      <div class="log">
        <div v-for="(e, i) in beats" :key="i" class="beat" :class="{ sys: !e.actor }">
          <div class="beat-who" v-if="e.actor">
            <span class="who-name" :class="whoClass(e)">{{ e.actor_name }}</span>
            <span class="who-tag">{{ stanceLabel(e) }}</span>
          </div>
          <div class="beat-body">
            <div class="beat-input" v-if="e.action_text">
              <span class="inp-tag">action</span>{{ e.action_text }}
            </div>
            <div class="beat-input" v-if="e.reaction_text">
              <span class="inp-tag">回应</span><span class="inp-who" v-if="e.reactor_name">{{ e.reactor_name }}：</span>{{ e.reaction_text }}
            </div>
            <div v-if="e._pending" class="beat-narr muted">…裁决与叙事中…</div>
            <div v-else class="beat-narr">{{ e.narration }}</div>
          </div>
        </div>
      </div>

      <!-- gauge：各角色当前行动值（达门槛即可行动，最接近者排最前）；放在行动/状态区上方便于决策 -->
      <div class="actionstrip" v-if="snap.action_bar && snap.action_bar.length">
        <span class="strip-label muted">gauge</span>
        <template v-for="(b, i) in snap.action_bar" :key="b.id">
          <span v-if="i > 0" class="chsep">·</span>
          <span class="chip" :class="{ ready: b.gauge >= b.threshold }"
                :title="b.faction + (b.beats <= 0 ? ' · 可行动' : ' · ' + b.beats + ' 拍后')">
            {{ b.name }}
            <span class="cnum">{{ b.gauge }}/{{ b.threshold }}</span>
          </span>
        </template>
      </div>

      <div v-if="g.busy && !(snap.in_progress)" class="muted" style="margin-top:8px">…（裁决与叙事中，每拍约 10–15 秒）…</div>

      <!-- ended -->
      <div v-else-if="snap.ended" class="threat" style="margin-top:10px">场景结束：{{ snap.ended }}</div>

      <!-- 玩家行动 -->
      <div v-else-if="pendingType === 'player_action'" class="panel" style="margin-top:10px">
        <strong>轮到你行动（第 {{ snap.turn }} 拍）</strong>
        <label>你想做什么（一句话含做法；可附带小动作）</label>
        <textarea v-model="act.action" rows="2"
          placeholder="例：掀翻桌子撞向他 / 抄起油灯逼近 / 绕到背后贴墙摸近"></textarea>
        <div class="row">
          <div>
            <label>主要对象</label>
            <select v-model="act.target">
              <option value="">（无对象）</option>
              <option v-for="c in targets" :key="c.id" :value="c.id">{{ c.name }}（{{ c.faction }}）</option>
            </select>
          </div>
          <div>
            <label>covert？（想瞒过敌人才选）</label>
            <select v-model="act.covert">
              <option :value="false">否</option>
              <option :value="true">是（潜行/暗号/偷偷拔刀）</option>
            </select>
          </div>
        </div>
        <div class="suggest-box" v-if="g.suggesting || (g.suggestion && g.suggestion.kind === 'action')">
          <span class="muted small" v-if="g.suggesting">🤖 AI 思考中…</span>
          <template v-else>
            <div class="small"><b>🤖 AI 推荐（参考）</b> <a class="adopt" @click="adoptAction">采用</a></div>
            <div class="small">{{ g.suggestion.action }}<span class="muted" v-if="g.suggestion.target_name"> → {{ g.suggestion.target_name }}</span></div>
          </template>
        </div>
        <button style="margin-top:8px" @click="doAction" :disabled="g.busy">action</button>
      </div>

      <!-- 玩家回应 -->
      <div v-else-if="pendingType === 'player_reaction'" style="margin-top:10px">
        <div class="threat">⚔ {{ snap.pending.incoming }}<br>轮到你回应！</div>
        <div class="panel">
          <label>你要如何回应（闪避/格挡/反击/还嘴/喝止…，一句话含做法）</label>
          <textarea v-model="reaction" rows="2"
            placeholder="例：翻身滚到桌下 / 抬臂格开并反手一刀 / 冷笑回敬，趁他挪动欺身上前"></textarea>
          <div class="suggest-box" v-if="g.suggesting || (g.suggestion && g.suggestion.kind === 'reaction')">
            <span class="muted small" v-if="g.suggesting">🤖 AI 思考中…</span>
            <template v-else>
              <div class="small"><b>🤖 AI 推荐（参考）</b> <a class="adopt" @click="adoptReaction">采用</a></div>
              <div class="small">{{ g.suggestion.reaction }}</div>
            </template>
          </div>
          <button style="margin-top:8px" @click="doReact" :disabled="g.busy">回应</button>
        </div>
      </div>

      <details style="margin-top:12px">
        <summary class="muted">🔧 ledger_debug（含 gm 秘密，上帝视角）</summary>
        <pre>{{ snap.ledger_debug }}</pre>
      </details>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useGameStore } from '../stores/game'

const g = useGameStore()
const route = useRoute()
const snap = computed(() => g.snap)
const pendingType = computed(() => g.snap && g.snap.pending && g.snap.pending.type)
const targets = computed(() => (g.snap?.present || []).filter((c) => c.controller !== 'player'))
// 结构化每拍日志；旧存档无「log」时退回纯文本「public_log」
// 末尾追加「in_progress」拍（延迟遮盖：已揭示的可见行动/回应 + 「裁决中」占位），叙事到了被正式拍替换
const beats = computed(() => {
  const s = g.snap
  if (!s) return []
  const base = (s.log && s.log.length)
    ? s.log
    : (s.public_log || []).map((line) => ({ narration: line, actor: null }))
  return s.in_progress ? [...base, { ...s.in_progress, _pending: true }] : base
})
function factionClass(f) { return f === 'ally' ? 'ally' : (f === 'enemy' ? 'foe' : '') }
// 是不是玩家看「controller」，敌我看「faction」——都不依赖角色 id
function whoClass(e) { return e.controller === 'player' ? 'me' : factionClass(e.faction) }
function stanceLabel(e) {
  if (e.controller === 'player') return 'player'
  if (e.faction === 'ally') return '友方'
  if (e.faction === 'enemy') return '敌方'
  if (e.faction === 'neutral') return 'neutral'
  return e.faction || ''
}
// 角色面板边框：ally=ally(绿)、neutral=neutral(中性)、其余=foe(红)
function roleClass(c) { return c.is_ally ? 'ally' : (c.faction === 'neutral' ? 'neutral' : 'foe') }

const act = ref({ action: '', target: '', covert: false })
const reaction = ref('')

function hasMore(c) {
  return c.backstory || (c.personality && c.personality.length) || c.voice ||
    (c.tactics && c.tactics.length) || (c.inventory && c.inventory.length)
}

onMounted(async () => {
  const gid = route.params.gid
  if (!g.snap || g.snap.game_id !== gid) await g.load(gid)
})

// 到玩家决策点就拉「AI 替你演」的参考建议（页面先到、建议异步补）。串流中(busy)不触发、不每拍抖动。
watch(
  () => (snap.value && !g.busy) ? (pendingType.value + '#' + snap.value.turn) : 'idle',
  () => {
    if (!g.busy && (pendingType.value === 'player_action' || pendingType.value === 'player_reaction')) {
      g.fetchSuggestion()
    } else {
      g.suggestion = null
    }
  },
  { immediate: true }
)

function adoptAction() {
  const s = g.suggestion
  if (!s) return
  act.value = { action: s.action || '', target: s.target_id || '', covert: !!s.covert }
}
function adoptReaction() {
  if (g.suggestion) reaction.value = g.suggestion.reaction || ''
}

async function doAction() {
  const a = { action: act.value.action.trim() || '按兵不动', target: act.value.target || null, covert: act.value.covert }
  act.value = { action: '', target: '', covert: false }
  try { await g.act(a) } catch (e) { alert('行动出错：' + e.message) }
}

async function doReact() {
  const r = { reaction: reaction.value.trim() || '硬抗' }
  reaction.value = ''
  try { await g.react(r) } catch (e) { alert('回应出错：' + e.message) }
}
</script>

<style scoped>
.suggest-box {
  margin-top: 8px;
  padding: 6px 8px;
  border: 1px dashed var(--line);
  border-radius: 6px;
  background: #15130f;
}
.suggest-box .adopt { cursor: pointer; color: var(--gold); text-decoration: underline; margin-left: 6px; }
</style>
