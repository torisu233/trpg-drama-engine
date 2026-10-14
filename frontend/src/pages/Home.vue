<template>
  <div>
    <div class="row-between">
      <h2>Scenarios</h2>
      <button @click="create">+ New scenario</button>
    </div>
    <div class="cards">
      <div class="card" v-for="sc in s.list" :key="sc.id">
        <div class="card-title">
          {{ sc.title }}
          <span class="tag">{{ sc.visibility === 'published' ? 'Published' : 'Private' }}</span>
        </div>
        <div class="card-desc" v-if="sc.background">{{ sc.background }}</div>
        <div class="muted" v-if="admin && sc.author">Author: {{ sc.author }}</div>
        <div class="card-actions">
          <button @click="play(sc.id)" :disabled="!!starting">
            {{ starting === sc.id ? 'Loading…' : 'Play' }}
          </button>
          <button v-if="sc.is_mine || admin" class="mini" @click="router.push('/author/' + sc.id)">Edit</button>
          <button v-if="!sc.is_mine" class="mini" @click="copyScenario(sc.id)" :disabled="copying === sc.id">
            {{ copying === sc.id ? 'Copying…' : 'Copy & adapt' }}
          </button>
          <button v-if="sc.is_mine || admin" class="mini" @click="delScenario(sc.id, sc.title)">Delete</button>
        </div>
      </div>
      <div v-if="!s.list.length" class="muted">(No scenarios yet. Click "New scenario" to start.)</div>
    </div>

    <h2>My games{{ admin ? ' (admin: all)' : '' }}</h2>
    <div class="cards">
      <div class="card" v-for="g in game.games" :key="g.game_id">
        <div class="card-title">{{ g.scenario_name || g.game_id }}</div>
        <div class="muted">Beat {{ g.turn }}{{ g.ended ? ' · Ended' : '' }}
          <template v-if="admin && g.owner"> · Player: {{ g.owner }}</template>
        </div>
        <div class="card-actions">
          <button @click="router.push('/play/' + g.game_id)">Continue</button>
          <button class="mini" @click="delGame(g.game_id)">Delete</button>
        </div>
      </div>
      <div v-if="!game.games.length" class="muted">(None)</div>
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
    alert('Could not start: ' + e.message)
  } finally {
    starting.value = null
  }
}

async function copyScenario(id) {
  copying.value = id
  try {
    const newId = await s.copy(id)
    router.push('/author/' + newId)   // open the copy in the editor
  } catch (e) {
    alert('Copy failed: ' + e.message)
  } finally {
    copying.value = null
  }
}

async function delScenario(id, title) {
  if (!confirm(`Delete scenario "${title}"?`)) return
  try { await s.remove(id) } catch (e) { alert('Delete failed: ' + e.message) }
}
async function delGame(gid) {
  if (!confirm('Delete this saved game?')) return
  try { await game.remove(gid) } catch (e) { alert('Delete failed: ' + e.message) }
}
</script>
