const API = ""; // 同源（由 uvicorn 掛載）

async function post(path, body) {
  const r = await fetch(API + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return r.json();
}
async function get(path) { return (await fetch(API + path)).json(); }

function render(s) {
  if (!s.started) { document.getElementById("log").textContent = "點「開始」載入場景。"; return; }
  // 日誌
  const log = document.getElementById("log");
  log.innerHTML = s.公開日誌.map(line => {
    const cls = line.startsWith("【") ? "sys" : "";
    return `<div class="turn ${cls}">${escapeHtml(line)}</div>`;
  }).join("");
  log.scrollTop = log.scrollHeight;

  document.getElementById("view").textContent = s.玩家視圖 || "";
  document.getElementById("debug").textContent = s.帳本除錯 || "";

  // 輸入區
  const box = document.getElementById("input");
  if (s.結束) {
    box.innerHTML = `<div class="threat">場景結束：${escapeHtml(s.結束)}</div>`;
    return;
  }
  const p = s.pending;
  if (!p) { box.innerHTML = `<p class="muted">（推進中…）</p>`; return; }

  if (p.type === "player_action") {
    box.innerHTML = `
      <div class="panel">
        <strong>輪到你行動（第 ${s.回合數} 拍）</strong>
        <label>你想做什麼（一句話含做法；可附帶小動作，如攻擊同時對阿青使眼色）</label>
        <textarea id="act" rows="2" placeholder="例：佯攻刀疤、同時對阿青使眼色要他繞後 / 抄起油燈逼近他"></textarea>
        <div class="row">
          <div><label>主要對象</label>
            <select id="tgt">
              <option value="">（無對象）</option>
              <option value="scar">刀疤(敵)</option>
              <option value="aqing">阿青(隊友)</option>
            </select></div>
          <div><label>隱蔽？（想瞞過敵人才選）</label>
            <select id="hide"><option value="false">否</option><option value="true">是（潛行/暗號/偷偷拔刀）</option></select></div>
        </div>
        <button onclick="sendAction()">行動</button>
      </div>`;
  } else if (p.type === "player_reaction") {
    box.innerHTML = `
      <div class="threat">⚔ 刀疤對你出招/喊話：${escapeHtml(p.incoming || "")}<br>輪到你回應！</div>
      <div class="panel">
        <label>你要如何回應（閃避/格擋/反擊/還嘴/喝止…，一句話含做法）</label>
        <textarea id="react" rows="2" placeholder="例：翻身滾到桌下 / 抬臂格開並反手一刀 / 冷笑回敬，趁他挪動欺身上前"></textarea>
        <button onclick="sendReaction()">回應</button>
      </div>`;
  }
}

function escapeHtml(t){return (t||"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));}

async function start(){ render(await post("/api/start")); }
async function sendAction(){
  const action = {
    行動: val("act") || "按兵不動",
    目標: val("tgt") || null,
    隱蔽: val("hide") === "true",
  };
  document.getElementById("input").innerHTML = `<p class="muted">裁決中…</p>`;
  render(await post("/api/action", { action }));
}
async function sendReaction(){
  const reaction = { 反應: val("react") || "硬抗" };
  document.getElementById("input").innerHTML = `<p class="muted">裁決中…</p>`;
  render(await post("/api/react", { reaction }));
}
function val(id){ const e=document.getElementById(id); return e?e.value.trim():""; }

get("/api/state").then(render);
