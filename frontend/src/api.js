function withPw(opts = {}) {
  return { ...opts, headers: { ...(opts.headers || {}), 'X-App-Password': localStorage.getItem('app_pw') || '' } }
}

async function j(url, opts = {}) {
  let r = await fetch(url, withPw(opts))
  if (r.status === 401) {
    const pw = window.prompt('需要访问密码：')
    if (pw) {
      localStorage.setItem('app_pw', pw)
      r = await fetch(url, withPw(opts))   // 带上新密码重试一次
    }
  }
  if (!r.ok) throw new Error((await r.text()) || ('HTTP ' + r.status))
  return r.json()
}
const post = (url, body) =>
  j(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) })
const put = (url, body) =>
  j(url, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) })

// 串流 POST：每收到一行 NDJSON 就回呼一次 onSnap（逐拍更新画面）
async function postStream(url, body, onSnap) {
  const opts = { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) }
  let r = await fetch(url, withPw(opts))
  if (r.status === 401) {
    const pw = window.prompt('需要访问密码：')
    if (pw) { localStorage.setItem('app_pw', pw); r = await fetch(url, withPw(opts)) }
  }
  if (!r.ok) throw new Error((await r.text()) || ('HTTP ' + r.status))
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
  // 剧本 / 编剧
  listScenarios: () => j('/api/scenarios'),
  getScenario: (id) => j('/api/scenarios/' + encodeURIComponent(id)),
  saveScenario: (id, sc) => put('/api/scenarios/' + encodeURIComponent(id), sc),
  delScenario: (id) => j('/api/scenarios/' + encodeURIComponent(id), { method: 'DELETE' }),
  authorTurn: (scenario, history, message) => post('/api/author/turn', { scenario, history, message }),
  // 游玩
  listGames: () => j('/api/games'),
  newGame: (scenario_id) => post('/api/game/new', { scenario_id }),
  getGame: (gid) => j('/api/game/' + gid),
  delGame: (gid) => j('/api/game/' + gid, { method: 'DELETE' }),
  actionStream: (gid, action, onSnap) => postStream('/api/game/' + gid + '/action', { action }, onSnap),
  reactStream: (gid, reaction, onSnap) => postStream('/api/game/' + gid + '/react', { reaction }, onSnap),
}
