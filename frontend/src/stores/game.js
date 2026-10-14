import { defineStore } from 'pinia'
import { api } from '../api'

export const useGameStore = defineStore('game', {
  state: () => ({ games: [], snap: null, busy: false, suggestion: null, suggesting: false }),
  actions: {
    async fetchSuggestion() {
      // 玩家决策点才拉「AI 替你演」的参考行为；只读、不改局面。失败静默，不挡手动。
      const s = this.snap
      const t = s && s.pending && s.pending.type
      if (!s || s.ended || (t !== 'player_action' && t !== 'player_reaction')) { this.suggestion = null; return }
      const gid = s.game_id, turn = s.turn
      this.suggestion = null
      this.suggesting = true
      try {
        const r = await api.suggest(gid)
        // 竞态守卫：回来时局面已变（已行动/换拍）就丢弃
        if (this.snap && this.snap.game_id === gid && this.snap.turn === turn) {
          this.suggestion = (r && r.suggestion) || null
        }
      } catch (_) {
        this.suggestion = null
      } finally {
        this.suggesting = false
      }
    },
    async refreshGames() {
      this.games = (await api.listGames()).games
    },
    async start(scenarioId) {
      this.snap = await api.newGame(scenarioId)
      return this.snap
    },
    async load(gid) {
      this.snap = await api.getGame(gid)
    },
    async act(action) {
      this.busy = true
      this.suggestion = null            // 提交即清掉参考建议
      try {
        await api.actionStream(this.snap.game_id, action, (snap) => { this.snap = snap })  // 逐拍更新
      } finally {
        this.busy = false
      }
    },
    async react(reaction) {
      this.busy = true
      this.suggestion = null
      try {
        await api.reactStream(this.snap.game_id, reaction, (snap) => { this.snap = snap })
      } finally {
        this.busy = false
      }
    },
    async remove(gid) {
      await api.delGame(gid)
      await this.refreshGames()
    },
  },
})
