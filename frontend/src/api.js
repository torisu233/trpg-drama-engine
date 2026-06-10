function withPw(opts = {}) {
  return { ...opts, headers: { ...(opts.headers || {}), 'X-App-Password': localStorage.getItem('app_pw') || '' } }
}

async function j(url, opts = {}) {
  let r = await fetch(url, withPw(opts))
  if (r.status === 401) {
    const pw = window.prompt('需要存取密碼：')
    if (pw) {
      localStorage.setItem('app_pw', pw)
      r = await fetch(url, withPw(opts))   // 帶上新密碼重試一次
    }
  }
  if (!r.ok) throw new Error((await r.text()) || ('HTTP ' + r.status))
  return r.json()
}
const post = (url, body) =>
  j(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) })
const put = (url, body) =>
  j(url, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) })

export const api = {
  // 劇本 / 編劇
  listScenarios: () => j('/api/scenarios'),
  getScenario: (id) => j('/api/scenarios/' + encodeURIComponent(id)),
  saveScenario: (id, sc) => put('/api/scenarios/' + encodeURIComponent(id), sc),
  delScenario: (id) => j('/api/scenarios/' + encodeURIComponent(id), { method: 'DELETE' }),
  authorTurn: (scenario, history, message) => post('/api/author/turn', { scenario, history, message }),
  // 遊玩
  listGames: () => j('/api/games'),
  newGame: (scenario_id) => post('/api/game/new', { scenario_id }),
  getGame: (gid) => j('/api/game/' + gid),
  action: (gid, action) => post('/api/game/' + gid + '/action', { action }),
  react: (gid, reaction) => post('/api/game/' + gid + '/react', { reaction }),
}
