import { defineStore } from 'pinia'
import { api } from '../api'

export function emptyScenario(id = 'Untitled scenario') {
  return {
    id,
    world: { tone: '', background: '', laws: [] },
    scene: { id: 'scene', location: '', hook: '', present: [] },
    cards: {},
    ledger: { characters: {}, scene: { spatial: [], scene_facts: [], social_facts: [] }, faction_private: {} },
  }
}

export const useScenarioStore = defineStore('scenario', {
  state: () => ({
    list: [],                 // [{id,title,visibility,author,is_mine}]
    draft: emptyScenario(),   // scenario content (held client-side until saved)
    currentId: null,          // DB id being edited; null = new
    visibility: 'private',    // private | published
    history: [],
    busy: false,
    lastMissing: [],
    lastDone: false,
  }),
  actions: {
    async refreshList() {
      this.list = (await api.listScenarios()).scenarios
    },
    newDraft() {
      this.draft = emptyScenario()
      this.currentId = null
      this.visibility = 'private'
      this.history = []
      this.lastMissing = []
      this.lastDone = false
    },
    async loadDraft(id) {
      const r = await api.getScenario(id)   // {id,title,visibility,content,...}
      this.draft = r.content
      this.currentId = r.id
      this.visibility = r.visibility
      this.history = []
      this.lastMissing = []
      this.lastDone = false
    },
    async sendMessage(msg) {
      this.history.push({ role: 'User', text: msg })
      this.busy = true
      try {
        const r = await api.authorTurn(this.draft, this.history, msg)
        this.draft = r.scenario
        this.lastMissing = r.missing || []
        this.lastDone = !!r.done
        this.history.push({ role: 'Writer', text: r.reply, meta: { block: r.block, char_id: r.char_id } })
        return r
      } finally {
        this.busy = false
      }
    },
    async save() {
      const body = { scenario: this.draft, visibility: this.visibility }
      if (this.currentId) {
        await api.updateScenario(this.currentId, body)
      } else {
        const r = await api.createScenario(body)
        this.currentId = r.id
      }
      await this.refreshList()
      return this.currentId
    },
    async remove(id) {
      await api.delScenario(id)
      await this.refreshList()
    },
    async copy(id) {
      const r = await api.copyScenario(id)   // server clones it as my private copy
      await this.refreshList()
      return r.id
    },
  },
})
