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

      <div class="log">
        <div v-for="(line, i) in snap.公开日志" :key="i"
             class="turn" :class="{ sys: line.startsWith('【') }">{{ line }}</div>
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
        <summary class="muted">你感知到的局面</summary>
        <pre>{{ snap.玩家视图 }}</pre>
      </details>
      <details>
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

const act = ref({ 行动: '', 目标: '', 隐蔽: false })
const reaction = ref('')

function pct(b) { return Math.min(100, Math.round((b.行动值 / b.门槛) * 100)) }

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
