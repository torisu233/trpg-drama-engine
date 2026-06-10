<template>
  <div>
    <div class="row-between">
      <h2>游玩</h2>
      <router-link to="/">← 返回剧本集</router-link>
    </div>

    <div v-if="!snap" class="muted">加载中…</div>
    <template v-else>
      <div class="actionstrip" v-if="snap.行动条 && snap.行动条.length">
        <span class="strip-label muted">行动序</span>
        <template v-for="(b, i) in snap.行动条" :key="b.id">
          <span v-if="i > 0" class="chsep">›</span>
          <span class="chip" :class="{ ready: b.行动值 >= b.门槛 }"
                :title="b.阵营 + (b.预估拍 <= 0 ? ' · 可行动' : ' · ' + b.预估拍 + ' 拍后')">
            {{ b.名 }}
            <span class="cnum">{{ b.行动值 }}/{{ b.门槛 }}</span>
            <span class="minibar"><span class="minifill" :style="{ width: pct(b) + '%' }"></span></span>
          </span>
        </template>
      </div>

      <!-- 你的局面（常驻置顶）-->
      <div class="panel situ" v-if="snap.局面">
        <div class="situ-line"><b>场景</b>{{ snap.局面.场景 }}</div>
        <div class="situ-line" v-if="snap.局面.场面 && snap.局面.场面.length"><b>场面</b>{{ snap.局面.场面.join('；') }}</div>
        <div class="situ-line" v-if="snap.局面.情报 && snap.局面.情报.length"><b>约定/情报</b>{{ snap.局面.情报.join('；') }}</div>
        <div class="situ-line muted" v-if="snap.局面.计策 && snap.局面.计策.length"><b>我方计策</b>{{ snap.局面.计策.join('；') }}</div>
      </div>

      <!-- 在场角色：我方详尽 / 敌方仅可见 -->
      <div class="cards rolecards" v-if="snap.角色 && snap.角色.length">
        <div v-for="c in snap.角色" :key="c.id" class="card role" :class="{ ally: c.是我方, foe: !c.是我方 }">
          <div class="card-title">
            {{ c.名 }}
            <span class="muted small">· {{ c.阵营 }}<template v-if="c.性别">·{{ c.性别 }}</template><template v-if="c.是自己">·你</template></span>
          </div>
          <div class="small muted">速度 {{ c.行动速度 }} · 感知 {{ c.感知能力 }}</div>
          <div class="small">{{ c.姿势位置 || '在场' }}</div>
          <div class="small" v-if="c.状态 && c.状态.length">状态：{{ c.状态.join('，') }}</div>
          <template v-if="c.是我方">
            <div class="small" v-if="c.能力 && c.能力.length"><b>能力</b> {{ c.能力.join('、') }}</div>
            <div class="small" v-if="c.防御特性 && c.防御特性.length"><b>防御</b> {{ c.防御特性.join('、') }}</div>
            <div class="small weak" v-if="c.弱点 && c.弱点.length"><b>弱点</b> {{ c.弱点.join('、') }}</div>
            <div class="small muted" v-if="c.动机目标"><b>动机</b> {{ c.动机目标 }}</div>
            <details v-if="hasMore(c)" class="more">
              <summary class="muted small">更多</summary>
              <div class="small" v-if="c.身分背景">身分：{{ c.身分背景 }}</div>
              <div class="small" v-if="c.性格 && c.性格.length">性格：{{ c.性格.join('、') }}</div>
              <div class="small" v-if="c.说话风格">说话：{{ c.说话风格 }}</div>
              <div class="small" v-if="c.行为偏好 && c.行为偏好.length">偏好：{{ c.行为偏好.join('、') }}</div>
              <div class="small" v-if="c.持有 && c.持有.length">持有：{{ c.持有.join('、') }}</div>
            </details>
          </template>
          <div class="small muted foe-hint" v-else>底细未知，靠观察判断</div>
        </div>
      </div>

      <div class="log">
        <div v-for="(e, i) in beats" :key="i" class="beat" :class="{ sys: !e.行动者 }">
          <div class="beat-who" v-if="e.行动者">
            <span class="who-name" :class="factionClass(e.阵营)">{{ e.行动者名 }}</span>
          </div>
          <div class="beat-body">
            <div class="beat-input" v-if="e.行动文本">
              <span class="inp-tag">行动</span>{{ e.行动文本 }}
            </div>
            <div class="beat-input" v-if="e.反应文本">
              <span class="inp-tag">回应</span><span class="inp-who" v-if="e.反应者名">{{ e.反应者名 }}：</span>{{ e.反应文本 }}
            </div>
            <div class="beat-narr">{{ e.叙事 }}</div>
          </div>
        </div>
      </div>

      <div v-if="g.busy" class="muted" style="margin-top:8px">…（裁决与叙事中，每拍约 10–15 秒）…</div>

      <!-- 结束 -->
      <div v-else-if="snap.结束" class="threat" style="margin-top:10px">场景结束：{{ snap.结束 }}</div>

      <!-- 玩家行动 -->
      <div v-else-if="pendingType === 'player_action'" class="panel" style="margin-top:10px">
        <strong>轮到你行动（第 {{ snap.回合数 }} 拍）</strong>
        <label>你想做什么（一句话含做法；可附带小动作）</label>
        <textarea v-model="act.行动" rows="2"
          placeholder="例：掀翻桌子撞向他 / 抄起油灯逼近 / 绕到背后贴墙摸近"></textarea>
        <div class="row">
          <div>
            <label>主要对象</label>
            <select v-model="act.目标">
              <option value="">（无对象）</option>
              <option v-for="c in targets" :key="c.id" :value="c.id">{{ c.名 }}（{{ c.阵营 }}）</option>
            </select>
          </div>
          <div>
            <label>隐蔽？（想瞒过敌人才选）</label>
            <select v-model="act.隐蔽">
              <option :value="false">否</option>
              <option :value="true">是（潜行/暗号/偷偷拔刀）</option>
            </select>
          </div>
        </div>
        <button style="margin-top:8px" @click="doAction" :disabled="g.busy">行动</button>
      </div>

      <!-- 玩家回应 -->
      <div v-else-if="pendingType === 'player_reaction'" style="margin-top:10px">
        <div class="threat">⚔ {{ snap.pending.incoming }}<br>轮到你回应！</div>
        <div class="panel">
          <label>你要如何回应（闪避/格挡/反击/还嘴/喝止…，一句话含做法）</label>
          <textarea v-model="reaction" rows="2"
            placeholder="例：翻身滚到桌下 / 擡臂格开并反手一刀 / 冷笑回敬，趁他挪动欺身上前"></textarea>
          <button style="margin-top:8px" @click="doReact" :disabled="g.busy">回应</button>
        </div>
      </div>

      <details style="margin-top:12px">
        <summary class="muted">🔧 帐本调试（含 gm 秘密，上帝视角）</summary>
        <pre>{{ snap.帐本调试 }}</pre>
      </details>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useGameStore } from '../stores/game'

const g = useGameStore()
const route = useRoute()
const snap = computed(() => g.snap)
const pendingType = computed(() => g.snap && g.snap.pending && g.snap.pending.type)
const targets = computed(() => (g.snap?.在场 || []).filter((c) => c.id !== 'player'))
// 结构化每拍日志；旧存档无「日志」时退回纯文本「公开日志」
const beats = computed(() => {
  const s = g.snap
  if (!s) return []
  if (s.日志 && s.日志.length) return s.日志
  return (s.公开日志 || []).map((line) => ({ 叙事: line, 行动者: null }))
})
function factionClass(f) { return f === '我方' ? 'ally' : (f === '敌' ? 'foe' : '') }

const act = ref({ 行动: '', 目标: '', 隐蔽: false })
const reaction = ref('')

function pct(b) { return Math.min(100, Math.round((b.行动值 / b.门槛) * 100)) }
function hasMore(c) {
  return c.身分背景 || (c.性格 && c.性格.length) || c.说话风格 ||
    (c.行为偏好 && c.行为偏好.length) || (c.持有 && c.持有.length)
}

onMounted(async () => {
  const gid = route.params.gid
  if (!g.snap || g.snap.game_id !== gid) await g.load(gid)
})

async function doAction() {
  const a = { 行动: act.value.行动.trim() || '按兵不动', 目标: act.value.目标 || null, 隐蔽: act.value.隐蔽 }
  act.value = { 行动: '', 目标: '', 隐蔽: false }
  try { await g.act(a) } catch (e) { alert('行动出错：' + e.message) }
}

async function doReact() {
  const r = { 反应: reaction.value.trim() || '硬抗' }
  reaction.value = ''
  try { await g.react(r) } catch (e) { alert('回应出错：' + e.message) }
}
</script>
