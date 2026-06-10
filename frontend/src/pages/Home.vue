<template>
  <div>
    <div class="row-between">
      <h2>剧本集</h2>
      <button @click="create">＋ 新建剧本</button>
    </div>
    <div class="cards">
      <div class="card" v-for="id in s.list" :key="id">
        <div class="card-title">{{ id }}</div>
        <div class="card-actions">
          <router-link :to="'/author/' + id">编辑</router-link>
          <button @click="play(id)" :disabled="!!starting">
            {{ starting === id ? '加载中…' : '游玩' }}
          </button>
          <button class="mini" @click="delScenario(id)">删除</button>
        </div>
      </div>
      <div v-if="!s.list.length" class="muted">（还没有剧本，点「新建剧本」开始）</div>
    </div>

    <h2>进行中的游戏</h2>
    <div class="cards">
      <div class="card" v-for="g in game.games" :key="g.game_id">
        <div class="card-title">{{ g.地点 || g.game_id }}</div>
        <div class="muted">第 {{ g.回合数 }} 拍{{ g.结束 ? ' · 已结束' : '' }}</div>
        <div class="card-actions">
          <router-link :to="'/play/' + g.game_id">续玩</router-link>
          <button class="mini" @click="delGame(g.game_id)">删除</button>
        </div>
      </div>
      <div v-if="!game.games.length" class="muted">（无）</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useScenarioStore } from '../stores/scenario'
import { useGameStore } from '../stores/game'

const s = useScenarioStore()
const game = useGameStore()
const router = useRouter()
const starting = ref('')

onMounted(() => { s.refreshList(); game.refreshGames() })

function create() { s.newDraft(); router.push('/author/') }

async function play(id) {
  starting.value = id
  try {
    const snap = await game.start(id)
    router.push('/play/' + snap.game_id)
  } catch (e) {
    alert('开始失败：' + e.message)
  } finally {
    starting.value = ''
  }
}

async function delScenario(id) {
  if (!confirm(`删除剧本「${id}」？`)) return
  try { await s.remove(id) } catch (e) { alert('删除失败：' + e.message) }
}
async function delGame(gid) {
  if (!confirm('删除这局游戏纪录？')) return
  try { await game.remove(gid) } catch (e) { alert('删除失败：' + e.message) }
}
</script>
