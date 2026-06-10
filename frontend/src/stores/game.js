import { defineStore } from 'pinia'
import { api } from '../api'

export const useGameStore = defineStore('game', {
  state: () => ({ games: [], snap: null, busy: false }),
  actions: {
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
      try {
        await api.actionStream(this.snap.game_id, action, (snap) => { this.snap = snap })  // 逐拍更新
      } finally {
        this.busy = false
      }
    },
    async react(reaction) {
      this.busy = true
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
