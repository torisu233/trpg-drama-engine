# 数据库 + Auth 设计（定稿）

把本地 JSON 存储迁到 **PostgreSQL（云端 RDS）/ SQLAlchemy**，并加用户 auth。本地先做好再上云。

## 总原则
- **DB 是唯一真相**：除 **admin 账号、API key（来自环境变量）** 外，所有数据都在 DB。
- **剧本只存 DB**，由用户经编剧页/接口创建；DB 初始化**不再 seed 任何示范剧本**。`scenarios/*.json` 只是开发者参考样例（运行时不读）。
- **软删除**：不物理删行，用 `is_active` 字段标记启用/停用；查询默认 `is_active=true`。
- **本地、测试、云端皆 PostgreSQL**（dev/prod 行为一致，不用 SQLite）：本地用 `docker-compose.yml` 起 PG（主机端口 **5433**，避开本机原生 PG 占的 5432），云端 RDS；靠 `DATABASE_URL` 切换。起库：`docker compose up -d --wait`。
- DB 列名用英文（驱动/工具/Alembic 友好）；JSON 内容仍是中文 Pydantic dump。

## 三张表
**users**：`id`(PK) · `username`(unique) · `password_hash`(bcrypt) · `is_admin`(bool) · `is_active`(bool, 软删) · `created_at`

**scenarios**：`id`(int PK) · `title` · `author_id`(FK users) · `visibility`(`private`/`published`, 默认 private) · `content`(JSON=整个 Scenario) · `is_active` · `created_at`/`updated_at`

**games**（游玩历史，**永远私人**）：`id`(str PK, uuid) · `user_id`(FK users) · `scenario_id`(FK scenarios, 可空) · `state`(JSON=整个 Session) · `turn_count`/`ended`(列表显示用) · `is_active` · `created_at`/`updated_at`

关系：user 1—N scenarios（作者）/ games（拥有）；scenario 1—N games（来源，软删后游戏仍自带 Session 可玩）。

## 权限 / 可见性
| 操作 | 规则 |
|---|---|
| 列剧本 | `published` 或 `author_id=我`；**admin 看全部** |
| 读剧本 | published 人人可读；private 仅作者/admin |
| 改/删剧本 | 仅作者 / admin（删=软删 `is_active=false`） |
| 游戏 列/读/删 | 仅 `user_id=我` / admin（永远私人） |
| **admin** | 看到并操作**所有**剧本与游玩历史；**前端在 admin 登录时显示每项的持有者(username)** |

## Auth
- 注册 `POST /api/auth/register {username,password}`（开放自助，username 3–32、password ≥6）→ bcrypt 哈希 → 发 JWT。
- 登录 `POST /api/auth/login` → 发 **JWT**（含 user_id + is_admin，`JWT_SECRET` 签，TTL 7 天，无 refresh）。
- `GET /api/auth/me` → 当前用户（前端探测 + 取 is_admin 决定是否显示持有者）。
- 请求带 `Authorization: Bearer <jwt>`，**取代 `X-App-Password` 闸**。公开端点：`/api/health`、`/api/auth/register`、`/api/auth/login`。
- admin **不进 DB 用户表**？→ 不，admin 是 DB 里的普通 user（`is_admin=true`），开机用 `ADMIN_USERNAME`/`ADMIN_PASSWORD` 幂等 seed。
- 登出 = 前端丢 token。localStorage + Bearer（接受 XSS 代价）。

## 环境变量变化
- **移除** `APP_PASSWORD`（被 auth 取代）。
- **新增** `DATABASE_URL`、`JWT_SECRET`、`ADMIN_USERNAME`、`ADMIN_PASSWORD`。
- 保留 LLM 密钥 `LLM_API_KEY`（旧名 GROK_API_KEY）。

## 架构要点
- **移除 `game_store._cache`**：DB 为唯一真相，每请求从 DB 载入→改→存回；串流时逐拍存回。多 ECS task 才一致（这正是上云要 DB 的原因）。
- 并发改同一局 = last-write-wins（回合制单人，先不做乐观锁）。
- Alembic **从头用**：schema 改动有迁移纪录、不丢数据。

## 构建顺序（本地、逐步验证）
1. **DB 地基**：`db.py`（engine/Session/Base/get_db）+ `models_db.py`（User/Scenario/Game）+ config `DATABASE_URL` + Alembic 首版迁移。
2. **auth**：register/login/me + JWT + `current_user`/`current_admin` 依赖 + seed admin。
3. **剧本→DB**：list/get/create/update/delete + 可见性/拥有权（剧本由用户自建存 DB；不 seed 示范剧本）。
4. **游戏→DB**：移除 _cache、create/get/save/list/delete 绑 user。
5. **前端**：登录/注册 + Bearer + 整数 id + admin 显示持有者。
6. **测试**：DB fixture（连本地 docker PG 的测试库）+ auth fixture，重写 test_api/test_scenario；CI 加 `services: postgres` 容器跑测试（与生产同引擎）。
7.（之后）RDS + 注入新 env + 部署。

## 后续功能（Part 2 之后，已实现）
- **复制剧本**：`POST /api/scenarios/{sid}/copy` —— 校验可读(published/自己/admin)→ 克隆为我的 `private` 副本（标题加「（副本）」）。无新表。
- **改密码**：`POST /api/auth/change-password {old_password,new_password}` —— 先验旧密码再存新哈希；JWT 无状态、不含密码，改后旧 token 仍有效到期。
- **反馈聊天**（第 4 张表）：**feedback_messages** —— `id`(PK) · `thread_user_id`(FK users，会话属于哪个普通用户) · `sender_is_admin`(bool) · `body`(text) · `is_read`(bool，admin 是否已读该用户消息) · `created_at`。一普通用户一条会话线、统一对「admin」。
  - 用户端 `GET/POST /api/feedback`（`current_user`，只碰自己那条线）；admin 端 `GET /api/feedback/threads`（列表+未读）、`GET /api/feedback/{user_id}`（读并标已读）、`POST /api/feedback/{user_id}`（回复），皆 `current_admin`。**权限全在后端，前端按角色显示入口只是 UX。**
  - 前端统一独立页面：用户 `/feedback`、admin `/admin/feedback`（左用户列表+右对话），共用 `ChatThread` 组件；打开载入 + 8 秒轮询（无 websocket，小规模够用）。
  - 新迁移 `f159fc1ec85e_feedback_messages`；云端靠容器启动 `alembic upgrade head` 自动建表。
