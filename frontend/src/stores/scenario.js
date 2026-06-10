import { defineStore } from 'pinia'
import { api } from '../api'

export function emptyScenario(id = '未命名') {
  return {
    id,
    世界观: { 基调: '', 背景: '', 法则: [] },
    scene: { id: 'scene', 地点: '', 钩子: '', 在场: [] },
    角色卡: {},
    会变层: { 角色: {}, 场景: { 空间关系: [], 场景事实: [], 社会事实: [] }, 阵营私有: {} },
  }
}

export const useScenarioStore = defineStore('scenario', {
  state: () => ({
    list: [],
    draft: emptyScenario(),   // 草稿正本（前端持有，存盘才落地）
    history: [],              // 与编剧的对话 [{role,text,meta?}]
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
      this.history.push({ role: '用户', text: msg })
      this.busy = true
      try {
        const r = await api.authorTurn(this.draft, this.history, msg)
        this.draft = r.scenario   // agent 改过的整份剧本，直接替换正本
        this.lastMissing = r.missing || []
        this.lastDone = !!r.done
        this.history.push({ role: '编剧', text: r.reply, meta: { 区块: r.区块, char_id: r.char_id } })
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
