import { defineStore } from 'pinia'
import { api } from '../api'

export function emptyScenario(id = '未命名剧本') {
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
    list: [],                 // [{id,title,visibility,author,is_mine}]
    draft: emptyScenario(),   // 剧本内容（前端持有，存盘才落地）
    currentId: null,          // 正在编辑的 DB id；null=新建
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
      this.history.push({ role: '用户', text: msg })
      this.busy = true
      try {
        const r = await api.authorTurn(this.draft, this.history, msg)
        this.draft = r.scenario
        this.lastMissing = r.missing || []
        this.lastDone = !!r.done
        this.history.push({ role: '编剧', text: r.reply, meta: { 区块: r.区块, char_id: r.char_id } })
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
  },
})
