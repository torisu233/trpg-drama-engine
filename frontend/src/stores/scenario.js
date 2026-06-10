import { defineStore } from 'pinia'
import { api } from '../api'

export function emptyScenario(id = '未命名') {
  return {
    id,
    世界觀: { 基調: '', 背景: '', 法則: [] },
    scene: { id: 'scene', 地點: '', 鉤子: '', 在場: [] },
    角色卡: {},
    會變層: { 角色: {}, 場景: { 空間關係: [], 場景事實: [], 社會事實: [] }, 陣營私有: {} },
  }
}

export const useScenarioStore = defineStore('scenario', {
  state: () => ({
    list: [],
    draft: emptyScenario(),   // 草稿正本（前端持有，存檔才落地）
    history: [],              // 與編劇的對話 [{role,text,meta?}]
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
      this.history = []
      this.lastMissing = []
      this.lastDone = false
    },
    async loadDraft(id) {
      this.draft = await api.getScenario(id)
      this.history = []
      this.lastMissing = []
      this.lastDone = false
    },
    async sendMessage(msg) {
      this.history.push({ role: '使用者', text: msg })
      this.busy = true
      try {
        const r = await api.authorTurn(this.draft, this.history, msg)
        this.draft = r.scenario   // agent 改過的整份劇本，直接替換正本
        this.lastMissing = r.missing || []
        this.lastDone = !!r.done
        this.history.push({ role: '編劇', text: r.reply, meta: { 區塊: r.區塊, char_id: r.char_id } })
        return r
      } finally {
        this.busy = false
      }
    },
    async save(id) {
      this.draft.id = id
      await api.saveScenario(id, this.draft)
      await this.refreshList()
    },
    async remove(id) {
      await api.delScenario(id)
      await this.refreshList()
    },
  },
})
