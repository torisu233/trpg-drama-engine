# TRPG 原型 · 戏剧引擎跑团

依 [`docs/设计文档.md`](docs/设计文档.md) 的**戏剧引擎**（状态帐本 + LLM 裁决取代骰子数值）做的多 agent 跑团原型。两大功能：**剧本设计**（编剧 agent）与**实际游玩**。

## 架构

```
backend/
  ── 内核（框架无关）──
  models.py     数据模型：World/CharCard/Ledger/Session/Scenario + LLM I/O
  config.py     平衡常数（行动条/运气/摘要/整理门槛/温度）
  grok_client.py  Grok（openai SDK + instructor，自动重问）
  engine.py     行动条 / 两轴 / 迷雾 / delta / TTL / 帐本整理辅助
  agents.py     裁决 / 叙事 / 角色意图+反应 / 摘要 / 整理 / 编剧
  flow.py       开局推进 + 串流逐拍 + 每拍维护（TTL/整理/摘要）
  scenario.py   剧本访问（list/load/save）+ session 转换 + 编剧套用
  ── API（FastAPI）──
  main.py       app 入口（纯 API）
  deps.py       共用 Grok client
  game_store.py 游戏场次 + JSON 存盘
  routes/       scenarios.py（CRUD+编剧）, game.py（游玩）
  ── 测试 / 诊断 ──
  smoke_test.py  纯逻辑回归(10项)     api_smoke.py   脱机 API（TestClient，自带酒馆 fixture）
  stream_test.py 串流逐拍验证(live)   mode_test.py   非战斗模式验证(live)
  author_test.py 编剧 agent 验证(live)
  scene.py       in-code 酒馆 session（脱机测试 fixture）
scenarios/      剧本（编剧产物，版控）  *.json
data/games/     游戏存盘（运行期，gitignore）  *.json
frontend/       Vue 3 SPA（Vite+Pinia+Router）：剧本集 / 编剧页 / 游玩页
publish.ps1     一键 Cloudflare 隧道公开（密码闸）
```

## 安装
```powershell
cd trpg-drama-engine
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# .env 需有 GROK_API_KEY（见 .env.example）
```

## 跑起来

**1) API 服务器**（终端机 A）
```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8100
# Swagger 文档：http://127.0.0.1:8100/docs
```

**2) 前端 Vue dev server**（终端机 B）
```powershell
cd frontend
npm install        # 首次
npm run dev        # http://localhost:5173 （/api 自动代理到 8100）
```
两个都跑着，浏览器开 **http://localhost:5173**：剧本集 → 新建/编辑（聊天+面板）→ 游玩。
（游玩与编剧都只走前后端；已无命令行入口。）

**测试**
```powershell
.\.venv\Scripts\python.exe -m backend.smoke_test   # 纯逻辑 10 项
.\.venv\Scripts\python.exe -m backend.api_smoke     # 脱机 API（不打 grok）
```

## 临时分享到公网（Cloudflare 隧道，免注册）

把整个 app（前端＋API 已是同一个服务）用 Cloudflare 快速隧道公开，一键：
```powershell
.\publish.ps1
```
会问你设一个**访问密码** → 自动建置前端、起后端、开隧道，印出 `https://xxxx.trycloudflare.com`。
把**网址＋密码**分享出去，对方开网址、输入密码即可玩。`Ctrl+C` 结束分享。

注意：
- **你的机器要开着**（隧道指向本机）；关机/Ctrl+C 就断。
- 公开时**务必有密码**（`publish.ps1` 会强制）——否则任何人都能烧你的 Grok 密钥。
- 对方游玩的 Grok 调用都算**你的帐上**。
- Cloudflare 快速隧道**每次网址都不同**（随机、拋弃式）；要固定网址见下。

## 固定网址分享（ngrok，每次同一网址）

Cloudflare 快速隧道每次随机；想要**每次发布都同一个网址**（方便长期分享），用 ngrok 免费固定子网域。

一次性设置：
1. 到 https://ngrok.com 注册免费帐号，复制 authtoken
2. 安装：`winget install ngrok.ngrok`
3. 存 token：`ngrok config add-authtoken <你的TOKEN>`
4. 到 https://dashboard.ngrok.com/domains 保留一个免费网域（形如 `your-name.ngrok-free.app`）

之后每次发布：
```powershell
.\publish-ngrok.ps1
```
首次会问**访问密码**与**保留的网域**（记进 `.ngrok-domain.txt`，之后不必再输）→ 重建前端、起后端、用固定网址开隧道。
网址永远是 `https://your-name.ngrok-free.app`。`Ctrl+C` 结束。

注意：
- 同样**机器要开着、务必有密码**（脚本强制）。
- ngrok 免费版首次开网页会有一次「Visit Site」警告页，点一下即可（API 的 fetch 请求不受影响）。

## API

**剧本／编剧（无状态，前端持有草稿）**
| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/scenarios` | 列出剧本 |
| GET | `/api/scenarios/{id}` | 读一份 |
| PUT | `/api/scenarios/{id}` | 存/覆写（手动编辑也走这） |
| DELETE | `/api/scenarios/{id}` | 删除 |
| POST | `/api/author/turn` | 编剧对话：`{scenario,history,message}` → `{reply, scenario(已合并), 区块, missing, done}` |

**游玩（有状态，后端存盘）**
| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/games` | 进行中清单 |
| POST | `/api/game/new` | `{scenario_id}` → `{game_id, snapshot}` |
| GET | `/api/game/{id}` | 取 snapshot |
| POST | `/api/game/{id}/action` | `{action:{行动,目标,隐蔽}}` → **NDJSON 串流**（逐拍 snapshot） |
| POST | `/api/game/{id}/react` | `{reaction:{反应}}` → **NDJSON 串流**（逐拍 snapshot） |
| DELETE | `/api/game/{id}` | 删除游戏 |

snapshot = `{game_id, 回合数, 结束, pending, 公开日志, 在场, 行动条, 玩家视图, 帐本调试}`。

> 公开分享时设 `APP_PASSWORD`，则 `/api/*`（health 除外）须带 header `X-App-Password`。

## 路线图
- [x] 内核戏剧引擎（行动条/两轴/裁决/叙事/迷雾/摘要/帐本整理）
- [x] 世界观法则 + 双用角色卡（含秘密弱点）+ 社会事实长期记忆
- [x] 模式中立 prompt（对话/交涉/潜入皆适用）+ 叙事丰富度
- [x] 剧本数据层 + 编剧 agent + 全可编辑编剧页
- [x] 后端 API 化（编剧无状态 / 游玩有状态 + JSON 存盘）
- [x] Vue 3 前端：剧本集（可删）/ 编剧页 / 游玩页
- [x] 游玩逐拍串流显示 + 实时行动条（单行胶囊）
- [x] 一键公网分享（Cloudflare 隧道 + 密码闸）
- [ ] 批量叙事（多 NPC 拍揉成一段，文气更佳）
- [ ] 上云 24/7 部署（目前为临时隧道）
