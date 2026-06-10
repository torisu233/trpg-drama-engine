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
        this.snap = await api.action(this.snap.game_id, action)
      } finally {
        this.busy = false
      }
    },
    async react(reaction) {
      this.busy = true
      try {
        this.snap = await api.react(this.snap.game_id, reaction)
      } finally {
        this.busy = false
      }
    },
  },
})
