import { auth, clearSession } from './auth'

function authHeaders(extra = {}) {
  const h = { ...extra }
  if (auth.token) h['Authorization'] = 'Bearer ' + auth.token
  return h
}

async function _err(r) {
  let msg = 'HTTP ' + r.status
  try { const e = await r.json(); if (e && e.detail) msg = e.detail } catch (_) {}
  return new Error(msg)
}

async function j(url, opts = {}) {
  const r = await fetch(url, { ...opts, headers: authHeaders(opts.headers) })
  if (r.status === 401) { clearSession(); throw new Error('Not signed in, or your session has expired') }
  if (!r.ok) throw await _err(r)
  return r.status === 204 ? null : r.json()
}
const post = (url, body) =>
  j(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) })
const put = (url, body) =>
  j(url, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) })

// Streaming POST: calls onSnap once per NDJSON line (beat-by-beat updates)
async function postStream(url, body, onSnap) {
  const r = await fetch(url, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body || {}),
  })
  if (r.status === 401) { clearSession(); throw new Error('Not signed in, or your session has expired') }
  if (!r.ok) throw await _err(r)
  const reader = r.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    let nl
    while ((nl = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, nl).trim()
      buf = buf.slice(nl + 1)
      if (line) _emit(JSON.parse(line), onSnap)
    }
  }
  const last = buf.trim()
  if (last) _emit(JSON.parse(last), onSnap)
}

// A stream line is either a snapshot or a final {error} (the backend already saved the last completed beat)
function _emit(obj, onSnap) {
  if (obj && obj.error) throw new Error(obj.error)
  onSnap(obj)
}

export const api = {
  // auth
  register: (username, password) => post('/api/auth/register', { username, password }),
  login: (username, password) => post('/api/auth/login', { username, password }),
  me: () => j('/api/auth/me'),
  changePassword: (old_password, new_password) => post('/api/auth/change-password', { old_password, new_password }),
  // scenarios
  listScenarios: () => j('/api/scenarios'),
  getScenario: (id) => j('/api/scenarios/' + id),
  createScenario: (body) => post('/api/scenarios', body),         // {scenario, visibility}
  updateScenario: (id, body) => put('/api/scenarios/' + id, body),
  delScenario: (id) => j('/api/scenarios/' + id, { method: 'DELETE' }),
  copyScenario: (id) => post('/api/scenarios/' + id + '/copy'),   // clone as my private copy
  authorTurn: (scenario, history, message) => post('/api/author/turn', { scenario, history, message }),
  // play
  listGames: () => j('/api/games'),
  newGame: (scenario_id) => post('/api/game/new', { scenario_id }),
  getGame: (gid) => j('/api/game/' + gid),
  delGame: (gid) => j('/api/game/' + gid, { method: 'DELETE' }),
  actionStream: (gid, action, onSnap) => postStream('/api/game/' + gid + '/action', { action }, onSnap),
  reactStream: (gid, reaction, onSnap) => postStream('/api/game/' + gid + '/react', { reaction }, onSnap),
  continueStream: (gid, onSnap) => postStream('/api/game/' + gid + '/continue', {}, onSnap),
  suggest: (gid) => j('/api/game/' + gid + '/suggest'),   // AI suggests a move for the player (read-only)
  // feedback: user side (own thread only)
  feedbackMine: () => j('/api/feedback'),
  feedbackSend: (body) => post('/api/feedback', { body }),
  // feedback: admin side (all threads)
  feedbackThreads: () => j('/api/feedback/threads'),
  feedbackThread: (uid) => j('/api/feedback/' + uid),
  feedbackReply: (uid, body) => post('/api/feedback/' + uid, { body }),
}
