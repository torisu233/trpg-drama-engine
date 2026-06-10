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
  flow.py       推進迴圈 + 每拍維護（TTL/整理/摘要）
  scene.py      手寫種子場景（酒館）
  scenario.py   劇本存取（list/load/save）+ session 轉換 + 編劇套用
  ── API（FastAPI）──
  main.py       app 入口（純 API）
  deps.py       共用 Grok client
  game_store.py 遊戲場次 + JSON 存檔
  routes/       scenarios.py（CRUD+編劇）, game.py（遊玩）
  ── CLI / 診斷 ──
  play.py       命令行遊玩    author.py   命令行編劇
  smoke_test.py 純邏輯回歸    api_smoke.py 離線 API 測試
  trace_test.py 逐環節追蹤    live_*.py    端到端 live
scenarios/      劇本（編劇產物，版控）  *.json
data/games/     遊戲存檔（執行期，gitignore）  *.json
frontend/       （舊 vanilla 頁，將由 Vue 取代）
```

## 安裝
```powershell
cd trpg-drama-engine
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# .env 需有 GROK_API_KEY（見 .env.example）
```

## 跑起來

**API 伺服器**（Vue 前端將跨域呼叫它）
```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8100
# Swagger 文件：http://127.0.0.1:8100/docs
```

**命令行工具**（免前端即可玩/編）
```powershell
.\.venv\Scripts\python.exe -m backend.play     # 玩（目前載入酒館）
.\.venv\Scripts\python.exe -m backend.author   # 編劇：對話設計劇本，/save 存檔
```

**測試**
```powershell
.\.venv\Scripts\python.exe -m backend.smoke_test   # 純邏輯 9 項
.\.venv\Scripts\python.exe -m backend.api_smoke     # 離線 API（不打 grok）
```

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
| POST | `/api/game/{id}/action` | `{action:{行動,目標,隱蔽}}` → snapshot |
| POST | `/api/game/{id}/react` | `{reaction:{反應}}` → snapshot |

snapshot = `{game_id, 回合數, 結束, pending, 公開日誌, 玩家視圖, 帳本除錯}`。

## 路線圖
- [x] 核心戲劇引擎（行動條/兩軸/裁決/敘事/迷霧/摘要/整理）
- [x] 劇本資料層 + 編劇 agent + CLI
- [x] 後端 API 化（編劇無狀態 / 遊玩有狀態 + JSON 存檔）
- [ ] **Vue 3 前端**：劇本清單 / 編劇頁（聊天+面板綁草稿）/ 遊玩頁
- [ ] 串流逐拍顯示、批次敘事（敘事品質增強）
