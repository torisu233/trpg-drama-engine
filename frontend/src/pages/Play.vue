<template>
  <div>
    <div class="row-between">
      <h2>遊玩</h2>
      <router-link to="/">← 返回劇本集</router-link>
    </div>

    <div v-if="!snap" class="muted">載入中…</div>
    <template v-else>
      <div class="panel" v-if="snap.行動條 && snap.行動條.length">
        <div class="card-title">行動順序（越上面越快輪到）</div>
        <div v-for="b in snap.行動條" :key="b.id" class="barrow">
          <span class="bname">{{ b.名 }}<span class="muted">（{{ b.陣營 }}）</span></span>
          <div class="bar"><div class="fill" :class="{ ready: b.行動值 >= b.門檻 }" :style="{ width: pct(b) + '%' }"></div></div>
          <span class="bnum muted">{{ b.行動值 }}/{{ b.門檻 }}<template v-if="b.預估拍 <= 0"> · 可行動</template><template v-else> · {{ b.預估拍 }} 拍後</template></span>
        </div>
      </div>

      <div class="log">
        <div v-for="(line, i) in snap.公開日誌" :key="i"
             class="turn" :class="{ sys: line.startsWith('【') }">{{ line }}</div>
      </div>

      <div v-if="g.busy" class="muted" style="margin-top:8px">…（裁決與敘事中，每拍約 10–15 秒）…</div>

      <!-- 結束 -->
      <div v-else-if="snap.結束" class="threat" style="margin-top:10px">場景結束：{{ snap.結束 }}</div>

      <!-- 玩家行動 -->
      <div v-else-if="pendingType === 'player_action'" class="panel" style="margin-top:10px">
        <strong>輪到你行動（第 {{ snap.回合數 }} 拍）</strong>
        <label>你想做什麼（一句話含做法；可附帶小動作）</label>
        <textarea v-model="act.行動" rows="2"
          placeholder="例：掀翻桌子撞向他 / 抄起油燈逼近 / 繞到背後貼牆摸近"></textarea>
        <div class="row">
          <div>
            <label>主要對象</label>
            <select v-model="act.目標">
              <option value="">（無對象）</option>
              <option v-for="c in targets" :key="c.id" :value="c.id">{{ c.名 }}（{{ c.陣營 }}）</option>
            </select>
          </div>
          <div>
            <label>隱蔽？（想瞞過敵人才選）</label>
            <select v-model="act.隱蔽">
              <option :value="false">否</option>
              <option :value="true">是（潛行/暗號/偷偷拔刀）</option>
            </select>
          </div>
        </div>
        <button style="margin-top:8px" @click="doAction" :disabled="g.busy">行動</button>
      </div>

      <!-- 玩家回應 -->
      <div v-else-if="pendingType === 'player_reaction'" style="margin-top:10px">
        <div class="threat">⚔ {{ snap.pending.incoming }}<br>輪到你回應！</div>
        <div class="panel">
          <label>你要如何回應（閃避/格擋/反擊/還嘴/喝止…，一句話含做法）</label>
          <textarea v-model="reaction" rows="2"
            placeholder="例：翻身滾到桌下 / 抬臂格開並反手一刀 / 冷笑回敬，趁他挪動欺身上前"></textarea>
          <button style="margin-top:8px" @click="doReact" :disabled="g.busy">回應</button>
        </div>
      </div>

      <details style="margin-top:12px">
        <summary class="muted">你感知到的局面</summary>
        <pre>{{ snap.玩家視圖 }}</pre>
      </details>
      <details>
        <summary class="muted">🔧 帳本除錯（含 gm 秘密，上帝視角）</summary>
        <pre>{{ snap.帳本除錯 }}</pre>
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
const targets = computed(() => (g.snap?.在場 || []).filter((c) => c.id !== 'player'))

const act = ref({ 行動: '', 目標: '', 隱蔽: false })
const reaction = ref('')

function pct(b) { return Math.min(100, Math.round((b.行動值 / b.門檻) * 100)) }

onMounted(async () => {
  const gid = route.params.gid
  if (!g.snap || g.snap.game_id !== gid) await g.load(gid)
})

async function doAction() {
  const a = { 行動: act.value.行動.trim() || '按兵不動', 目標: act.value.目標 || null, 隱蔽: act.value.隱蔽 }
  act.value = { 行動: '', 目標: '', 隱蔽: false }
  try { await g.act(a) } catch (e) { alert('行動出錯：' + e.message) }
}

async function doReact() {
  const r = { 反應: reaction.value.trim() || '硬抗' }
  reaction.value = ''
  try { await g.react(r) } catch (e) { alert('回應出錯：' + e.message) }
}
</script>
