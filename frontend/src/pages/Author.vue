<template>
  <div>
    <div class="row-between">
      <h2>Writer · {{ d.id }}</h2>
      <div class="row" style="gap:8px; flex:0 0 auto;">
        <input v-model="d.id" style="width:140px" placeholder="Scenario name" />
        <select v-model="s.visibility" style="width:100px">
          <option value="private">Private</option>
          <option value="published">Published</option>
        </select>
        <button @click="save" :disabled="s.busy">Save</button>
        <router-link to="/" class="back-btn">← Back</router-link>
      </div>
    </div>

    <div v-if="s.lastMissing.length" class="muted">Still missing:
      <span class="tag" v-for="m in s.lastMissing" :key="m">{{ m }}</span>
    </div>
    <div v-if="s.lastDone" class="tag" style="color:var(--gold)">✓ Complete enough to save</div>

    <div class="split" style="margin-top:10px">
      <!-- Left: fully editable panels -->
      <div>
        <!-- world -->
        <details class="panel sec" open>
          <summary>World</summary>
          <div class="field"><label>Tone</label><input v-model="d.world.tone" placeholder="e.g. wuxia, martial-world feuds" /></div>
          <div class="field"><label>Background (~150 words)</label><textarea v-model="d.world.background" rows="3"></textarea></div>
          <div class="field"><label>Laws (affect rulings · common knowledge)</label>
            <div class="hint muted small">Laws are this world's public rules: the adjudicator and every character can see them, so never put any side's secrets here. For secrets, use a character's "Weaknesses" or a GM-only scene fact in the initial ledger.</div>
            <StrListEditor v-model="d.world.laws" ph="A world law" label="Add law" />
          </div>
        </details>

        <!-- scene -->
        <details class="panel sec" open>
          <summary>Scene</summary>
          <div class="field"><label>ID</label><input v-model="d.scene.id" /></div>
          <div class="field"><label>Location</label><input v-model="d.scene.location" /></div>
          <div class="field"><label>Opening hook</label><textarea v-model="d.scene.hook" rows="2"></textarea></div>
          <div class="field"><label>Character IDs present</label>
            <StrListEditor v-model="d.scene.present" ph="Character ID, e.g. player" label="Add to scene" />
          </div>
        </details>

        <!-- cards -->
        <details class="panel sec" open>
          <summary>Characters ({{ Object.keys(d.cards).length }})</summary>
          <div v-for="(c, id) in d.cards" :key="id" class="subcard">
            <div class="row-between">
              <strong>{{ c.name || '(unnamed)' }} <span class="muted">[{{ id }}]</span></strong>
              <button class="mini" @click="removeChar(id)">Delete character</button>
            </div>
            <div class="row">
              <div><label>Name</label><input v-model="c.name" /></div>
              <div><label>Gender</label><input v-model="c.gender" /></div>
            </div>
            <div class="row">
              <div><label>Faction</label>
                <select v-model="c.faction">
                  <option v-for="(lbl, code) in FACTION_LABELS" :key="code" :value="code">{{ lbl }}</option>
                </select>
              </div>
              <div><label>Controller</label>
                <select v-model="c.controller">
                  <option v-for="(lbl, code) in CONTROLLER_LABELS" :key="code" :value="code">{{ lbl }}</option>
                </select>
              </div>
            </div>
            <label>Backstory (incl. appearance and age)</label><textarea v-model="c.backstory" rows="2"></textarea>
            <label>Directive (hard floor · top priority, fed only to the character AI)</label>
            <textarea v-model="c.directive" rows="2"
              placeholder="Only 1–3 core rules that must be followed to the letter (e.g. &quot;Never betray the player&quot;, &quot;Firmly believes they are the chosen one&quot;). Put everyday personality and voice in the structured fields below; piling on rules makes the character wooden. Shapes the persona only, never overrides game rules."></textarea>
            <label>Voice</label><input v-model="c.voice" />
            <label>Motive</label><input v-model="c.motive" />
            <label>Personality</label><StrListEditor v-model="c.personality" label="Add" />
            <label>Tactics</label><StrListEditor v-model="c.tactics" label="Add" />
            <label>Abilities</label><StrListEditor v-model="c.abilities" label="Add" />
            <label>Defenses</label><StrListEditor v-model="c.defenses" label="Add" />
            <label>Weaknesses (may hold secrets; pair with GM-only clues in the ledger)</label><StrListEditor v-model="c.weaknesses" label="Add" />
          </div>
          <div class="row" style="margin-top:8px">
            <input v-model="newCharId" placeholder="New character ID (e.g. qing)" />
            <button @click="addChar">+ Add character</button>
          </div>
        </details>

        <!-- initial state -->
        <details class="panel sec">
          <summary>Initial state (ledger)</summary>
          <label>Scene · Spatial</label><CondListEditor v-model="d.ledger.scene.spatial" />
          <label>Scene · Scene facts (GM-only secrets allowed)</label><CondListEditor v-model="d.ledger.scene.scene_facts" />
          <label>Scene · Social facts (debts, promises, grudges)</label><CondListEditor v-model="d.ledger.scene.social_facts" />

          <div class="subcard" v-for="(cl, id) in d.ledger.characters" :key="'L'+id">
            <strong class="muted">Character state [{{ id }}]</strong>
            <label>Posture</label><input v-model="cl.posture" />
            <div class="row">
              <div><label>Speed</label><input type="number" v-model.number="cl.speed" /></div>
              <div><label>Perception</label><input v-model="cl.perception" /></div>
              <div><label>Starting gauge (initiative)</label><input type="number" v-model.number="cl.gauge" /></div>
            </div>
            <label>Conditions</label><CondListEditor v-model="cl.conditions" />
            <label>Status effects (bound, unconscious, etc.)</label><CondListEditor v-model="cl.status_effects" />
          </div>
          <div class="row" style="margin-top:8px">
            <select v-model="newLedgerId">
              <option value="">Initialize state for a character…</option>
              <option v-for="id in ledgerCandidates" :key="id" :value="id">{{ id }}</option>
            </select>
            <button @click="addLedger" :disabled="!newLedgerId">+ Add state</button>
          </div>
          <div class="muted" style="margin-top:6px">Items, carried gear, faction-private plans and other details can be edited in "Raw JSON" below.</div>
        </details>

        <!-- raw JSON catch-all editor -->
        <details class="panel sec">
          <summary>Advanced: raw JSON (edit anything)</summary>
          <button class="mini" @click="loadJson">⤵ Load current scenario</button>
          <button class="mini" @click="applyJson">Apply JSON</button>
          <textarea v-model="jsonText" rows="14" style="margin-top:6px; font-size:12px"></textarea>
          <div v-if="jsonErr" class="threat" style="margin-top:6px">{{ jsonErr }}</div>
        </details>
      </div>

      <!-- Right: chat with the writer -->
      <div>
        <div class="panel" style="display:flex; flex-direction:column; height:560px; position:sticky; top:10px">
          <div class="card-title">Chat with the writer</div>
          <div class="chat" ref="chatEl" style="flex:1">
            <div v-if="!s.history.length" class="muted">
              Tell me the scenario you want: world, scene, characters… I'll ask as I go and fill it in; the left panel updates live.<br>
              Example: "Wuxia. A down-on-his-luck escort guard is cornered by old enemies at an inn, with a reckless female companion."
            </div>
            <div v-for="(h, i) in s.history" :key="i" :class="h.role === 'User' ? 'me' : 'ai'">
              <strong>{{ h.role }}: </strong>{{ h.text }}
              <span v-if="h.meta && h.meta.block && h.meta.block !== 'none'" class="tag">
                Edited {{ h.meta.block }}{{ h.meta.char_id ? '/' + h.meta.char_id : '' }}
              </span>
            </div>
            <div v-if="s.busy" class="muted">… (the writer is thinking) …</div>
          </div>
          <div style="margin-top:8px">
            <textarea v-model="msg" rows="2" placeholder="Talk to the writer… (Enter to send, Shift+Enter for a new line)"
              @keydown.enter.exact.prevent="send"></textarea>
            <button style="margin-top:6px" @click="send" :disabled="s.busy || !msg.trim()">Send</button>
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

// enum code -> display label
const FACTION_LABELS = { ally: 'Ally', enemy: 'Enemy', neutral: 'Neutral' }
const CONTROLLER_LABELS = { player: 'Player', agent: 'AI agent' }

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
    try { await s.loadDraft(id) } catch (e) { alert('Load failed: ' + e.message); router.push('/') }
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
  } catch (e) { jsonErr.value = 'JSON parse error: ' + e.message }
}

async function send() {
  const t = msg.value.trim()
  if (!t || s.busy) return
  msg.value = ''
  try { await s.sendMessage(t) } catch (e) { alert('Writer error: ' + e.message) }
}
async function save() {
  if (!d.value.id || !d.value.id.trim()) { alert('Enter a scenario name first'); return }
  try {
    const wasNew = !s.currentId
    const id = await s.save()
    if (wasNew) router.push('/author/' + id)   // after creating, carry the id so later saves are updates
    alert('Saved')
  } catch (e) { alert('Save failed: ' + e.message) }
}
</script>

<style scoped>
/* "Back" outline button: same height and style as "Save" (solid button), using project vars --line/--gold */
.back-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 7px 13px;                 /* = button's 8px 14px minus the 1px border -> same height */
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
