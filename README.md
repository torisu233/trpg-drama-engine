# TRPG 原型 · 戲劇引擎跑團

依 [`docs/設計文件.md`](docs/設計文件.md) 的**戲劇引擎**（狀態帳本 + LLM 裁決取代骰子數值）做的多 agent 跑團原型。兩大功能：**劇本設計**（編劇 agent）與**實際遊玩**。

## 架構

```
backend/
  ── 核心（框架無關）──
  models.py     資料模型：World/CharCard/Ledger/Session/Scenario + LLM I/O
  config.py     平衡常數（行動條/運氣/摘要/整理門檻/溫度）
  grok_client.py  Grok（openai SDK + instructor，自動重問）
  engine.py     行動條 / 兩軸 / 迷霧 / delta / TTL / 帳本整理輔助
  agents.py     裁決 / 敘事 / 角色意圖+反應 / 摘要 / 整理 / 編劇
  flow.py       開局推進 + 串流逐拍 + 每拍維護（TTL/整理/摘要）
  scenario.py   劇本存取（list/load/save）+ session 轉換 + 編劇套用
  ── API（FastAPI）──
  main.py       app 入口（純 API）
  deps.py       共用 Grok client
  game_store.py 遊戲場次 + JSON 存檔
  routes/       scenarios.py（CRUD+編劇）, game.py（遊玩）
  ── 測試 / 診斷 ──
  smoke_test.py  純邏輯回歸(10項)     api_smoke.py   離線 API（TestClient，自帶酒館 fixture）
  stream_test.py 串流逐拍驗證(live)   mode_test.py   非戰鬥模式驗證(live)
  author_test.py 編劇 agent 驗證(live)
  scene.py       in-code 酒館 session（離線測試 fixture）
scenarios/      劇本（編劇產物，版控）  *.json
data/games/     遊戲存檔（執行期，gitignore）  *.json
frontend/       Vue 3 SPA（Vite+Pinia+Router）：劇本集 / 編劇頁 / 遊玩頁
publish.ps1     一鍵 Cloudflare 隧道公開（密碼閘）
```

## 安裝
```powershell
cd trpg-drama-engine
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# .env 需有 GROK_API_KEY（見 .env.example）
```

## 跑起來

**1) API 伺服器**（終端機 A）
```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8100
# Swagger 文件：http://127.0.0.1:8100/docs
```

**2) 前端 Vue dev server**（終端機 B）
```powershell
cd frontend
npm install        # 首次
npm run dev        # http://localhost:5173 （/api 自動代理到 8100）
```
兩個都跑著，瀏覽器開 **http://localhost:5173**：劇本集 → 新建/編輯（聊天+面板）→ 遊玩。
（遊玩與編劇都只走前後端；已無命令行入口。）

**測試**
```powershell
.\.venv\Scripts\python.exe -m backend.smoke_test   # 純邏輯 10 項
.\.venv\Scripts\python.exe -m backend.api_smoke     # 離線 API（不打 grok）
```

## 臨時分享到公網（Cloudflare 隧道，免註冊）

把整個 app（前端＋API 已是同一個服務）用 Cloudflare 快速隧道公開，一鍵：
```powershell
.\publish.ps1
```
會問你設一個**存取密碼** → 自動建置前端、起後端、開隧道，印出 `https://xxxx.trycloudflare.com`。
把**網址＋密碼**分享出去，對方開網址、輸入密碼即可玩。`Ctrl+C` 結束分享。

注意：
- **你的機器要開著**（隧道指向本機）；關機/Ctrl+C 就斷。
- 公開時**務必有密碼**（`publish.ps1` 會強制）——否則任何人都能燒你的 Grok 金鑰。
- 對方遊玩的 Grok 呼叫都算**你的帳上**。

## API

**劇本／編劇（無狀態，前端持有草稿）**
| 方法 | 路徑 | 作用 |
|---|---|---|
| GET | `/api/scenarios` | 列出劇本 |
| GET | `/api/scenarios/{id}` | 讀一份 |
| PUT | `/api/scenarios/{id}` | 存/覆寫（手動編輯也走這） |
| DELETE | `/api/scenarios/{id}` | 刪除 |
| POST | `/api/author/turn` | 編劇對話：`{scenario,history,message}` → `{reply, scenario(已合併), 區塊, missing, done}` |

**遊玩（有狀態，後端存檔）**
| 方法 | 路徑 | 作用 |
|---|---|---|
| GET | `/api/games` | 進行中清單 |
| POST | `/api/game/new` | `{scenario_id}` → `{game_id, snapshot}` |
| GET | `/api/game/{id}` | 取 snapshot |
| POST | `/api/game/{id}/action` | `{action:{行動,目標,隱蔽}}` → **NDJSON 串流**（逐拍 snapshot） |
| POST | `/api/game/{id}/react` | `{reaction:{反應}}` → **NDJSON 串流**（逐拍 snapshot） |
| DELETE | `/api/game/{id}` | 刪除遊戲 |

snapshot = `{game_id, 回合數, 結束, pending, 公開日誌, 在場, 行動條, 玩家視圖, 帳本除錯}`。

> 公開分享時設 `APP_PASSWORD`，則 `/api/*`（health 除外）須帶 header `X-App-Password`。

## 路線圖
- [x] 核心戲劇引擎（行動條/兩軸/裁決/敘事/迷霧/摘要/帳本整理）
- [x] 世界觀法則 + 雙用角色卡（含秘密弱點）+ 社會事實長期記憶
- [x] 模式中立 prompt（對話/交涉/潛入皆適用）+ 敘事豐富度
- [x] 劇本資料層 + 編劇 agent + 全可編輯編劇頁
- [x] 後端 API 化（編劇無狀態 / 遊玩有狀態 + JSON 存檔）
- [x] Vue 3 前端：劇本集（可刪）/ 編劇頁 / 遊玩頁
- [x] 遊玩逐拍串流顯示 + 即時行動條（單行膠囊）
- [x] 一鍵公網分享（Cloudflare 隧道 + 密碼閘）
- [ ] 批次敘事（多 NPC 拍揉成一段，文氣更佳）
- [ ] 上雲 24/7 部署（目前為臨時隧道）
