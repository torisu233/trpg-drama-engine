<template>
  <div>
    <div class="row-between">
      <h2>劇本集</h2>
      <button @click="create">＋ 新建劇本</button>
    </div>
    <div class="cards">
      <div class="card" v-for="id in s.list" :key="id">
        <div class="card-title">{{ id }}</div>
        <div class="card-actions">
          <router-link :to="'/author/' + id">編輯</router-link>
          <button @click="play(id)" :disabled="!!starting">
            {{ starting === id ? '載入中…' : '遊玩' }}
          </button>
        </div>
      </div>
      <div v-if="!s.list.length" class="muted">（還沒有劇本，點「新建劇本」開始）</div>
    </div>

    <h2>進行中的遊戲</h2>
    <div class="cards">
      <div class="card" v-for="g in game.games" :key="g.game_id">
        <div class="card-title">{{ g.地點 || g.game_id }}</div>
        <div class="muted">第 {{ g.回合數 }} 拍{{ g.結束 ? ' · 已結束' : '' }}</div>
        <div class="card-actions"><router-link :to="'/play/' + g.game_id">續玩</router-link></div>
      </div>
      <div v-if="!game.games.length" class="muted">（無）</div>
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
    alert('開始失敗：' + e.message)
  } finally {
    starting.value = ''
  }
}
</script>
