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
        <label>行動</label>
        <input id="act" placeholder="攻擊 / 說服 / 後撤 / 對話 / 移動 / 按兵不動…">
        <div class="row">
          <div><label>目標</label>
            <select id="tgt">
              <option value="">（無對象）</option>
              <option value="scar">刀疤(敵)</option>
              <option value="aqing">阿青(隊友)</option>
            </select></div>
          <div><label>隱蔽？</label>
            <select id="hide"><option value="false">否</option><option value="true">是（暗號/使眼色）</option></select></div>
        </div>
        <label>方式（具體怎麼做）</label>
        <textarea id="way" rows="2" placeholder="例：掀翻桌子撞向刀疤 / 拿油燈逼近他 / 低聲讓阿青繞到他背後"></textarea>
        <button onclick="sendAction()">行動</button>
      </div>`;
  } else if (p.type === "player_reaction") {
    box.innerHTML = `
      <div class="threat">⚔ 來襲：${escapeHtml(p.incoming || "")}<br>你必須反應！</div>
      <div class="panel">
        <label>反應類型</label>
        <input id="rtype" placeholder="閃避 / 格擋 / 反擊 / 硬抗 / 後仰躲開…">
        <label>方式</label>
        <textarea id="rway" rows="2" placeholder="例：翻身滾到桌下 / 抬臂格開並反手一刀"></textarea>
        <button onclick="sendReaction()">反應</button>
      </div>`;
  }
}

function escapeHtml(t){return (t||"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));}

async function start(){ render(await post("/api/start")); }
async function sendAction(){
  const action = {
    行動: val("act") || "按兵不動",
    目標: val("tgt") || null,
    方式: val("way"),
    隱蔽: val("hide") === "true",
  };
  document.getElementById("input").innerHTML = `<p class="muted">裁決中…</p>`;
  render(await post("/api/action", { action }));
}
async function sendReaction(){
  const reaction = { 類型: val("rtype") || "硬抗", 方式: val("rway") };
  document.getElementById("input").innerHTML = `<p class="muted">裁決中…</p>`;
  render(await post("/api/react", { reaction }));
}
function val(id){ const e=document.getElementById(id); return e?e.value.trim():""; }

get("/api/state").then(render);
