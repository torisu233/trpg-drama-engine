# TRPG 原型 · 戏剧引擎跑团

[![CI](https://github.com/torisu233/trpg-drama-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/torisu233/trpg-drama-engine/actions/workflows/ci.yml)

依 [`docs/设计文档.md`](docs/设计文档.md) 的**戏剧引擎**（状态账本 + LLM 裁决取代骰子数值）做的多 agent 跑团原型。两大功能：**剧本设计**（编剧 agent）与**实际游玩**。多用户（注册/登录），数据存 PostgreSQL，已上云（AWS ECS Express + RDS，见 [`docs/部署.md`](docs/部署.md)）。

## 架构

```
backend/
  ── 内核（框架无关）──
  models.py     数据模型：World/CharCard/Ledger/Session/Scenario + LLM I/O（中文字段）
  config.py     平衡常数（行动条/运气/摘要/整理门槛/温度）+ DATABASE_URL/JWT 设置
  grok_client.py  LLM 客户端（openai SDK 指向 DeepSeek，OpenAI 兼容 + instructor，自动重问）
  engine.py     行动条 / 两轴 / 迷雾 / delta / TTL / 账本整理辅助（纯函数）
  agents.py     裁决 / 叙事 / 角色意图+反应 / 摘要 / 整理 / 编剧
  flow.py       开局推进 + 串流逐拍 + 每拍维护（TTL/整理/摘要）
  scenario.py   Scenario↔Session 转换 + 编剧套用 + 首次 seed 武侠001
  ── 存储 / 鉴权 ──
  db.py         SQLAlchemy engine/SessionLocal/Base/get_db
  models_db.py  ORM 表：users / scenarios / games（软删除 + JSON 列）
  auth.py       bcrypt 哈希 + JWT 签发/校验 + current_user/admin + seed admin
  game_store.py 游戏场次（存 DB，绑 user）+ snapshot（喂前端）
  ── API（FastAPI）──
  main.py       app 入口（供前端 dist + /api；lifespan seed）
  deps.py       共用 Grok client
  routes/       auth.py（注册/登录/me）, scenarios.py（CRUD+编剧）, game.py（游玩）
  scene.py      in-code 酒馆 session（脱机测试 fixture）
  ── live 诊断脚本（会打 Grok，不在 CI）──
  mode_test.py 非战斗模式验证   author_test.py 编剧 agent 验证
alembic/        数据库迁移（版控；容器启动跑 alembic upgrade head）
tests/          pytest 套件（CI 跑；集成测试连真 PG）
  conftest.py（夹具）test_engine/test_flow/test_scenario/test_api.py
scenarios/      剧本种子（仅首次 seed 导入 DB 用）  武侠001.json
frontend/       Vue 3 SPA（Vite+Pinia+Router）：登录 / 剧本集 / 编剧页 / 游玩页
docker-compose.yml  本地 Postgres（host 5433）+ adminer
```

## 安装
```powershell
cd trpg-drama-engine
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt   # 含运行期 + pytest
Copy-Item .env.example .env        # 填 LLM_API_KEY；本机想要 admin 就填 ADMIN_PASSWORD
```

## 跑起来（本地三件套）

数据库、后端、前端分开跑。

**1) Postgres**（数据库，docker）
```powershell
docker compose up -d --wait        # 起 PG（host 5433）+ adminer（http://localhost:8888）
.\.venv\Scripts\python.exe -m alembic upgrade head   # 首次：建表
```

**2) API 服务器**（终端机 A）
```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8100
# Swagger：http://127.0.0.1:8100/docs   |   首启自动 seed admin（若设了 ADMIN_PASSWORD）+ 武侠001
```

**3) 前端 Vue dev server**（终端机 B）
```powershell
cd frontend
npm install        # 首次
npm run dev        # http://localhost:5173 （/api 自动代理到 8100）
```
浏览器开 **http://localhost:5173**：注册/登录 → 剧本集 → 新建/编辑（聊天+面板）→ 游玩。（皆走前后端，无命令行入口。）

**测试**（pytest）
```powershell
docker compose up -d --wait        # 集成测试连真 PG（独立测试库 trpg_test，不碰你的数据）
.\.venv\Scripts\python.exe -m pytest
```
纯逻辑测试（engine/flow/scenario）不连 DB；只有 `test_api` 需要 PG。策略见 [`tests/README.md`](tests/README.md)。

## 公开访问

**线上多用户版已部署在 AWS**（ECS Express + RDS）：`git push master` 即自动测试→build→推 ECR→上云。访问控制靠**用户 auth**（注册/登录 + JWT）。架构、AWS 资源、网络（app 公开子网 / RDS 私有子网 / 免 NAT）、启动迁移等见 [`docs/部署.md`](docs/部署.md)。

> 本机临时分享（隧道）方式已移除：要给别人玩就用云端 URL，或对方在你局域网内连你的 `:5173`/`:8100`。

## API

所有 `/api/*`（`/api/health` 与 `/api/auth/register`·`/login` 除外）都需带 `Authorization: Bearer <jwt>`。

**鉴权**
| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/api/auth/register` | `{username,password}` → `{token,username,is_admin}` |
| POST | `/api/auth/login` | 同上 |
| GET | `/api/auth/me` | 当前用户 |
| POST | `/api/auth/change-password` | `{old_password,new_password}`（验旧密码→存新哈希） |

**剧本／编剧**（剧本 id 为整数；private/published 可见性 + 拥有权）
| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/scenarios` | 列出（published 或自己的；admin 看全部） |
| GET | `/api/scenarios/{id}` | 读一份（含 content） |
| POST | `/api/scenarios` | 新建 `{scenario, visibility}` → `{id,...}` |
| POST | `/api/scenarios/{id}/copy` | 克隆可读剧本为我的私人副本（在别人发布的剧本上改） |
| PUT | `/api/scenarios/{id}` | 覆写（仅作者/admin） |
| DELETE | `/api/scenarios/{id}` | 软删除（仅作者/admin） |
| POST | `/api/author/turn` | 编剧对话：`{scenario,history,message}` → `{reply, scenario(已合并), 区块, missing, done}` |

**游玩**（有状态，存 DB；游戏永远私人）
| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/games` | 我的进行中清单（admin 看全部带 owner） |
| POST | `/api/game/new` | `{scenario_id}` → 开局 snapshot |
| GET | `/api/game/{id}` | 取 snapshot |
| POST | `/api/game/{id}/action` | `{action:{行动,目标,隐蔽}}` → **NDJSON 串流**（逐拍 snapshot） |
| POST | `/api/game/{id}/react` | `{reaction:{反应}}` → **NDJSON 串流** |
| DELETE | `/api/game/{id}` | 软删除（仅本人/admin） |

snapshot ≈ `{game_id, 回合数, 结束, pending, 公开日志, 日志(结构化逐拍), 在场, 行动条, 局面, 角色(我方详尽/敌方隐藏), 账本调试}`。

**反馈聊天**（用户↔admin；一用户一会话线，统一独立页面 `/feedback`、`/admin/feedback`）
| 方法 | 路径 | 作用 |
|---|---|---|
| GET/POST | `/api/feedback` | 用户读/发自己那条会话（`current_user`） |
| GET | `/api/feedback/threads` | admin：所有会话列表 + 未读数（`current_admin`） |
| GET | `/api/feedback/{user_id}` | admin：读某用户会话（打开即标已读） |
| POST | `/api/feedback/{user_id}` | admin：回复某用户 |

## 路线图
- [x] 内核戏剧引擎（行动条/两轴/裁决/叙事/迷雾/摘要/账本整理）
- [x] 世界观法则 + 双用角色卡（含秘密弱点）+ 社会事实长期记忆
- [x] 模式中立 prompt（对话/交涉/潜入皆适用）+ 叙事丰富度
- [x] 剧本数据层 + 编剧 agent + 全可编辑编剧页
- [x] Vue 3 前端：登录 / 剧本集 / 编剧页 / 游玩页
- [x] 游玩逐拍串流 + 实时行动条 + 玩家视图/角色面板 + 结构化逐拍日志
- [x] pytest 测试套件（单元+集成，集成连真 PG，74% 覆盖）
- [x] GitHub Actions CI（push 跑 pytest）+ Docker 多阶段镜像
- [x] **git push → 全自动上云**：CI 经 OIDC build→推 ECR→部署 AWS ECS Express（见 [`docs/部署.md`](docs/部署.md)）
- [x] JSON → PostgreSQL/SQLAlchemy + Alembic（云端 RDS 持久化）
- [x] 用户 auth 登录（注册/登录 + JWT，取代共享密码）
- [x] 复制别人发布的剧本来改；用户菜单（改密码 + 显示密码切换）
- [x] 反馈聊天（用户↔admin，统一独立页面 + 未读标记 + 8 秒轮询）
- [ ] 批量叙事（多 NPC 拍揉成一段，文气更佳）
