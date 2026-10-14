import { defineStore } from 'pinia'
import { api } from '../api'

export const useGameStore = defineStore('game', {
  state: () => ({ games: [], snap: null, busy: false, suggestion: null, suggesting: false }),
  actions: {
    async fetchSuggestion() {
      // Only fetch the "AI plays for you" suggestion at player decision points; read-only, never changes game state. Fails silently and never blocks manual input.
      const s = this.snap
      const t = s && s.pending && s.pending.type
      if (!s || s.ended || (t !== 'player_action' && t !== 'player_reaction')) { this.suggestion = null; return }
      const gid = s.game_id, turn = s.turn
      this.suggestion = null
      this.suggesting = true
      try {
        const r = await api.suggest(gid)
        // Race guard: drop the result if the game moved on (player acted / new beat) meanwhile
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
      this.suggestion = null            // submitting clears the suggestion
      await this._stream((gid, onSnap) => api.actionStream(gid, action, onSnap))  // beat-by-beat updates
    },
    async react(reaction) {
      this.suggestion = null
      await this._stream((gid, onSnap) => api.reactStream(gid, reaction, onSnap))
    },
    async cont() {
      await this._stream((gid, onSnap) => api.continueStream(gid, onSnap))
    },
    async _stream(call) {
      const gid = this.snap.game_id
      this.busy = true
      try {
        await call(gid, (snap) => { this.snap = snap })
      } catch (e) {
        // Drop any half-shown preview frame and show the last saved beat (the page then offers Continue)
        try { await this.load(gid) } catch (_) {}
        throw e
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
