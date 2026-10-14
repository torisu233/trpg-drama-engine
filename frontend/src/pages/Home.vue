<template>
  <div>
    <div class="row-between">
      <h2>剧本集</h2>
      <button @click="create">＋ 新建剧本</button>
    </div>
    <div class="cards">
      <div class="card" v-for="sc in s.list" :key="sc.id">
        <div class="card-title">
          {{ sc.title }}
          <span class="tag">{{ sc.visibility === 'published' ? '已发布' : '私人' }}</span>
        </div>
        <div class="card-desc" v-if="sc.background">{{ sc.background }}</div>
        <div class="muted" v-if="admin && sc.author">作者：{{ sc.author }}</div>
        <div class="card-actions">
          <button @click="play(sc.id)" :disabled="!!starting">
            {{ starting === sc.id ? '加载中…' : '游玩' }}
          </button>
          <button v-if="sc.is_mine || admin" class="mini" @click="router.push('/author/' + sc.id)">编辑</button>
          <button v-if="!sc.is_mine" class="mini" @click="copyScenario(sc.id)" :disabled="copying === sc.id">
            {{ copying === sc.id ? '复制中…' : '复制改编' }}
          </button>
          <button v-if="sc.is_mine || admin" class="mini" @click="delScenario(sc.id, sc.title)">删除</button>
        </div>
      </div>
      <div v-if="!s.list.length" class="muted">（还没有剧本，点「新建剧本」开始）</div>
    </div>

    <h2>我的游戏{{ admin ? '（管理员：all）' : '' }}</h2>
    <div class="cards">
      <div class="card" v-for="g in game.games" :key="g.game_id">
        <div class="card-title">{{ g.scenario_name || g.game_id }}</div>
        <div class="muted">第 {{ g.turn }} 拍{{ g.ended ? ' · 已结束' : '' }}
          <template v-if="admin && g.owner"> · player {{ g.owner }}</template>
        </div>
        <div class="card-actions">
          <button @click="router.push('/play/' + g.game_id)">续玩</button>
          <button class="mini" @click="delGame(g.game_id)">删除</button>
        </div>
      </div>
      <div v-if="!game.games.length" class="muted">（none）</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { auth } from '../auth'
import { useScenarioStore } from '../stores/scenario'
import { useGameStore } from '../stores/game'

const s = useScenarioStore()
const game = useGameStore()
const router = useRouter()
const starting = ref(null)
const copying = ref(null)
const admin = computed(() => !!(auth.user && auth.user.is_admin))

onMounted(() => { s.refreshList(); game.refreshGames() })

function create() { s.newDraft(); router.push('/author') }

async function play(id) {
  starting.value = id
  try {
    const snap = await game.start(id)
    router.push('/play/' + snap.game_id)
  } catch (e) {
    alert('开始失败：' + e.message)
  } finally {
    starting.value = null
  }
}

async function copyScenario(id) {
  copying.value = id
  try {
    const newId = await s.copy(id)
    router.push('/author/' + newId)   // 跳到副本编辑页
  } catch (e) {
    alert('复制失败：' + e.message)
  } finally {
    copying.value = null
  }
}

async function delScenario(id, title) {
  if (!confirm(`删除剧本「${title}」？`)) return
  try { await s.remove(id) } catch (e) { alert('删除失败：' + e.message) }
}
async function delGame(gid) {
  if (!confirm('删除这局游戏纪录？')) return
  try { await game.remove(gid) } catch (e) { alert('删除失败：' + e.message) }
}
</script>
