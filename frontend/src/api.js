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
  if (r.status === 401) { clearSession(); throw new Error('未登录或登录已过期') }
  if (!r.ok) throw await _err(r)
  return r.status === 204 ? null : r.json()
}
const post = (url, body) =>
  j(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) })
const put = (url, body) =>
  j(url, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) })

// 串流 POST：每行 NDJSON 回呼一次 onSnap（逐拍更新）
async function postStream(url, body, onSnap) {
  const r = await fetch(url, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body || {}),
  })
  if (r.status === 401) { clearSession(); throw new Error('未登录或登录已过期') }
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
      if (line) onSnap(JSON.parse(line))
    }
  }
  const last = buf.trim()
  if (last) onSnap(JSON.parse(last))
}

export const api = {
  // auth
  register: (username, password) => post('/api/auth/register', { username, password }),
  login: (username, password) => post('/api/auth/login', { username, password }),
  me: () => j('/api/auth/me'),
  changePassword: (old_password, new_password) => post('/api/auth/change-password', { old_password, new_password }),
  // 剧本
  listScenarios: () => j('/api/scenarios'),
  getScenario: (id) => j('/api/scenarios/' + id),
  createScenario: (body) => post('/api/scenarios', body),         // {scenario, visibility}
  updateScenario: (id, body) => put('/api/scenarios/' + id, body),
  delScenario: (id) => j('/api/scenarios/' + id, { method: 'DELETE' }),
  copyScenario: (id) => post('/api/scenarios/' + id + '/copy'),   // 克隆为我的私人副本
  authorTurn: (scenario, history, message) => post('/api/author/turn', { scenario, history, message }),
  // 游玩
  listGames: () => j('/api/games'),
  newGame: (scenario_id) => post('/api/game/new', { scenario_id }),
  getGame: (gid) => j('/api/game/' + gid),
  delGame: (gid) => j('/api/game/' + gid, { method: 'DELETE' }),
  actionStream: (gid, action, onSnap) => postStream('/api/game/' + gid + '/action', { action }, onSnap),
  reactStream: (gid, reaction, onSnap) => postStream('/api/game/' + gid + '/react', { reaction }, onSnap),
}
