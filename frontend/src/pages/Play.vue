<template>
  <div>
    <div class="row-between">
      <h2>Play</h2>
      <router-link to="/">← Back to scenarios</router-link>
    </div>

    <div v-if="!snap" class="muted">Loading…</div>
    <template v-else>
      <!-- Your situation (pinned at top) -->
      <div class="panel situ" v-if="snap.situation">
        <div class="situ-line"><b>Scene</b>{{ snap.situation.scene }}</div>
        <div class="situ-line" v-if="snap.situation.surroundings && snap.situation.surroundings.length"><b>Surroundings</b>{{ snap.situation.surroundings.join('; ') }}</div>
        <div class="situ-line" v-if="snap.situation.intel && snap.situation.intel.length"><b>Deals / intel</b>{{ snap.situation.intel.join('; ') }}</div>
        <div class="situ-line muted" v-if="snap.situation.plans && snap.situation.plans.length"><b>Our plans</b>{{ snap.situation.plans.join('; ') }}</div>
      </div>

      <!-- Characters present: full detail for allies / only what's visible for foes -->
      <div class="cards rolecards" v-if="snap.characters && snap.characters.length">
        <div v-for="c in snap.characters" :key="c.id" class="card role" :class="roleClass(c)">
          <div class="card-title">
            {{ c.name }}
            <span class="muted small">· {{ factionLabel(c.faction) }}<template v-if="c.gender"> · {{ c.gender }}</template><template v-if="c.is_self"> · You</template></span>
          </div>
          <div class="small muted">Speed {{ c.speed }} · Perception {{ perceptionLabel(c.perception) }}</div>
          <div class="small">{{ c.posture || 'Present' }}</div>
          <div class="small" v-if="c.state && c.state.length">State: {{ c.state.join(', ') }}</div>
          <template v-if="c.is_ally">
            <div class="small" v-if="c.abilities && c.abilities.length"><b>Abilities</b> {{ c.abilities.join(', ') }}</div>
            <div class="small" v-if="c.defenses && c.defenses.length"><b>Defenses</b> {{ c.defenses.join(', ') }}</div>
            <div class="small weak" v-if="c.weaknesses && c.weaknesses.length"><b>Weaknesses</b> {{ c.weaknesses.join(', ') }}</div>
            <div class="small muted" v-if="c.motive"><b>Motive</b> {{ c.motive }}</div>
            <details v-if="hasMore(c)" class="more">
              <summary class="muted small">More</summary>
              <div class="small" v-if="c.backstory">Backstory: {{ c.backstory }}</div>
              <div class="small" v-if="c.personality && c.personality.length">Personality: {{ c.personality.join(', ') }}</div>
              <div class="small" v-if="c.voice">Voice: {{ c.voice }}</div>
              <div class="small" v-if="c.tactics && c.tactics.length">Tactics: {{ c.tactics.join(', ') }}</div>
              <div class="small" v-if="c.inventory && c.inventory.length">Inventory: {{ c.inventory.join(', ') }}</div>
            </details>
          </template>
          <div class="small muted foe-hint" v-else>Background unknown; read them by what you observe</div>
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
              <span class="inp-tag">Action</span>{{ e.action_text }}
            </div>
            <div class="beat-input" v-if="e.reaction_text">
              <span class="inp-tag">Response</span><span class="inp-who" v-if="e.reactor_name">{{ e.reactor_name }}: </span>{{ e.reaction_text }}
            </div>
            <div v-if="e._pending" class="beat-narr muted">…adjudicating and narrating…</div>
            <div v-else class="beat-narr">{{ e.narration }}</div>
          </div>
        </div>
      </div>

      <!-- Gauge: each character's current action value (acts on reaching the threshold, closest first); sits above the action/status area to aid decisions -->
      <div class="actionstrip" v-if="snap.action_bar && snap.action_bar.length">
        <span class="strip-label muted">Gauge</span>
        <template v-for="(b, i) in snap.action_bar" :key="b.id">
          <span v-if="i > 0" class="chsep">·</span>
          <span class="chip" :class="{ ready: b.gauge >= b.threshold }"
                :title="factionLabel(b.faction) + (b.beats <= 0 ? ' · Ready' : ' · in ' + b.beats + (b.beats === 1 ? ' beat' : ' beats'))">
            {{ b.name }}
            <span class="cnum">{{ b.gauge }}/{{ b.threshold }}</span>
          </span>
        </template>
      </div>

      <div v-if="g.busy && !(snap.in_progress)" class="muted" style="margin-top:8px">… (adjudicating and narrating, about 10–15 seconds per beat) …</div>

      <!-- ended -->
      <div v-else-if="snap.ended" class="threat" style="margin-top:10px">Scene over: {{ snap.ended }}</div>

      <!-- Player action -->
      <div v-else-if="pendingType === 'player_action'" class="panel" style="margin-top:10px">
        <strong>Your move (beat {{ snap.turn }})</strong>
        <label>What do you do? (one sentence, including how; small extra moves are fine)</label>
        <textarea v-model="act.action" rows="2"
          placeholder="e.g. Flip the table into him / Grab the oil lamp and close in / Circle behind him, hugging the wall"></textarea>
        <div class="row">
          <div>
            <label>Main target</label>
            <select v-model="act.target">
              <option value="">(No target)</option>
              <option v-for="c in targets" :key="c.id" :value="c.id">{{ c.name }} ({{ factionLabel(c.faction) }})</option>
            </select>
          </div>
          <div>
            <label>Covert? (only if you want to hide it from enemies)</label>
            <select v-model="act.covert">
              <option :value="false">No</option>
              <option :value="true">Yes (sneaking / secret signal / quietly drawing a blade)</option>
            </select>
          </div>
        </div>
        <div class="suggest-box" v-if="g.suggesting || (g.suggestion && g.suggestion.kind === 'action')">
          <span class="muted small" v-if="g.suggesting">🤖 AI is thinking…</span>
          <template v-else>
            <div class="small"><b>🤖 AI suggestion (for reference)</b> <a class="adopt" @click="adoptAction">Use it</a></div>
            <div class="small">{{ g.suggestion.action }}<span class="muted" v-if="g.suggestion.target_name"> → {{ g.suggestion.target_name }}</span></div>
          </template>
        </div>
        <button style="margin-top:8px" @click="doAction" :disabled="g.busy">Act</button>
      </div>

      <!-- Player response -->
      <div v-else-if="pendingType === 'player_reaction'" style="margin-top:10px">
        <div class="threat">⚔ {{ snap.pending.incoming }}<br>Your turn to respond!</div>
        <div class="panel">
          <label>How do you respond? (dodge / block / counter / talk back / shout them down…, one sentence including how)</label>
          <textarea v-model="reaction" rows="2"
            placeholder="e.g. Roll under the table / Knock it aside and slash back / Sneer a retort and close in while he shifts"></textarea>
          <div class="suggest-box" v-if="g.suggesting || (g.suggestion && g.suggestion.kind === 'reaction')">
            <span class="muted small" v-if="g.suggesting">🤖 AI is thinking…</span>
            <template v-else>
              <div class="small"><b>🤖 AI suggestion (for reference)</b> <a class="adopt" @click="adoptReaction">Use it</a></div>
              <div class="small">{{ g.suggestion.reaction }}</div>
            </template>
          </div>
          <button style="margin-top:8px" @click="doReact" :disabled="g.busy">Respond</button>
        </div>
      </div>

      <!-- Interrupted mid-advance (an LLM call failed): resume from the last saved beat -->
      <div v-else-if="!g.busy" class="panel" style="margin-top:10px">
        <div class="muted small">The scene was interrupted before your next turn.</div>
        <button style="margin-top:8px" @click="doContinue" :disabled="g.busy">Continue</button>
      </div>

      <details style="margin-top:12px">
        <summary class="muted">🔧 Ledger debug (includes GM secrets, god's-eye view)</summary>
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
// Structured per-beat log; old saves without "log" fall back to plain-text "public_log"
// Append an "in_progress" beat at the end (deferred reveal: visible action/response so far + an "adjudicating" placeholder), replaced by the real beat once narration arrives
const beats = computed(() => {
  const s = g.snap
  if (!s) return []
  const base = (s.log && s.log.length)
    ? s.log
    : (s.public_log || []).map((line) => ({ narration: line, actor: null }))
  return s.in_progress ? [...base, { ...s.in_progress, _pending: true }] : base
})

// enum code -> display label (unknown codes fall through unchanged)
const FACTION_LABELS = { ally: 'Ally', enemy: 'Enemy', neutral: 'Neutral' }
const PERCEPTION_LABELS = { normal: 'Normal' }
function factionLabel(f) { return FACTION_LABELS[f] || f || '' }
function perceptionLabel(p) { return PERCEPTION_LABELS[p] || p || '' }

function factionClass(f) { return f === 'ally' ? 'ally' : (f === 'enemy' ? 'foe' : '') }
// "controller" decides whether it's the player, "faction" decides friend or foe; neither depends on character ids
function whoClass(e) { return e.controller === 'player' ? 'me' : factionClass(e.faction) }
function stanceLabel(e) {
  if (e.controller === 'player') return 'Player'
  return factionLabel(e.faction)
}
// Character card border: ally = ally (green), neutral = neutral (muted), everyone else = foe (red)
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

// At player decision points, fetch the "AI plays for you" suggestion (page renders first, suggestion fills in async). Not triggered while streaming (busy), so it doesn't flicker every beat.
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
  const a = { action: act.value.action.trim() || 'Hold position and wait', target: act.value.target || null, covert: act.value.covert }
  act.value = { action: '', target: '', covert: false }
  try { await g.act(a) } catch (e) { alert('Action error: ' + e.message) }
}

async function doReact() {
  const r = { reaction: reaction.value.trim() || 'Brace and take the hit' }
  reaction.value = ''
  try { await g.react(r) } catch (e) { alert('Response error: ' + e.message) }
}

async function doContinue() {
  try { await g.cont() } catch (e) { alert('Error: ' + e.message) }
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
