# 部署 · CI/CD → 云端（GCP Cloud Run + Cloud SQL）

`git push master` → 全自动测试、构建、推镜像、部署上云。本文记录架构、GCP 资源、流程与要点。
（历史：曾用 AWS ECS Express + RDS，2026-06 迁至 GCP。）

## 流水线（一张图）
```
git push master
   │
   ├─ test    pytest（连 CI 的 Postgres service container；不打 Grok）
   └─ deploy  WIF 换 GCP 凭证 → docker build → 推 Artifact Registry（tag: latest + git-sha）
              → gcloud run deploy（--add-cloudsql-instances 挂 Cloud SQL socket、以运行 SA 身份、注入 env）
              → 容器启动先 alembic upgrade head 建表，再 uvicorn
PR / 其他分支：只跑 test（CD 只从 master）
```
定义在 [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)。架构模式 = **Registry 驱动**：Actions 负责 CI + 构建 + 推 AR + 触发部署；Cloud Run 负责跑。

## 关键设计：无长期密钥（Workload Identity Federation）
CI 不存任何 GCP service-account 密钥。每次跑时，GitHub 签发短命 OIDC token，经 **WIF** 联合身份**模拟部署服务账号**换取临时凭证。
> 一句话：*"CI federates GitHub's OIDC token to impersonate a deploy service account — no static GCP keys in GitHub."*

## GCP 资源清单（project `<GCP_PROJECT_ID>` / number `<GCP_PROJECT_NUMBER>` / region `asia-northeast1`）
| 资源 | 名称/标识 | 作用 |
|---|---|---|
| Artifact Registry（docker） | `trpg` | 存镜像；路径 `asia-northeast1-docker.pkg.dev/<GCP_PROJECT_ID>/trpg/trpg` |
| Cloud Run 服务 | `trpg`（首次 deploy 时创建） | 跑容器、给公网 HTTPS `*.run.app`、缩容到零 |
| Cloud SQL Postgres 16 | `trpg-pg`（db-f1-micro、ZONAL、无备份） | 唯一数据真相（users/scenarios/games）；库 `trpg`、用户 `trpg` |
| 连接名 | `<GCP_PROJECT_ID>:asia-northeast1:trpg-pg` | Cloud Run `--add-cloudsql-instances` + DATABASE_URL socket |
| 运行 SA | `trpg-run@<GCP_PROJECT_ID>.iam.gserviceaccount.com` | Cloud Run 运行身份；`roles/cloudsql.client` |
| 部署 SA | `trpg-deployer@<GCP_PROJECT_ID>.iam.gserviceaccount.com` | GitHub 模拟；`run.admin` + `artifactregistry.writer` + 在运行 SA 上 `iam.serviceAccountUser`（actAs） |
| WIF 池 / provider | `github-pool` / `github-provider` | GitHub OIDC 信任；`attribute-condition` 限 `repository_owner=='torisu233'`，principalSet 绑 `torisu233/trpg-drama-engine` |

**线上 URL**：首次 deploy 后见 `deploy` job 末尾「打印服务 URL」步骤，或 `gcloud run services describe trpg --region asia-northeast1 --format='value(status.url)'`。

## 为什么不需要 VPC / 免网络配置
- Cloud Run 全托管，出网直连公网（拉 AR / 连 DeepSeek）——**无需 NAT、无需自建 VPC**。
- 连 Cloud SQL 用 **内建连接器**（`--add-cloudsql-instances` 挂 unix socket 到 `/cloudsql/<连接名>`）——**不需要私有 IP，也不需要 Serverless VPC 连接器**。比 AWS 那套（自建 VPC 公私子网）更省事。

## 密钥 / 配置（GitHub → Cloud Run env 注入）
仓库 `torisu233/trpg-drama-engine` → Settings → Secrets and variables → Actions：

**Variables（明文，`${{ vars.X }}`）**：`GCP_PROJECT_ID`、`GCP_REGION`、`GCP_WIF_PROVIDER`、`GCP_DEPLOY_SA`、`GCP_RUN_SA`、`GCP_SQL_CONN`、`GCP_IMAGE`、`ADMIN_USERNAME`。

**Secrets（加密，`${{ secrets.X }}`）**：
| secret | 作用 |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://trpg:<密码>@/trpg?host=/cloudsql/<GCP_PROJECT_ID>:asia-northeast1:trpg-pg`（socket 形；密码避免 URL 特殊字符或需编码） |
| `JWT_SECRET` | 签发/校验 JWT（`python3 -c "import secrets;print(secrets.token_hex(32))"`） |
| `ADMIN_PASSWORD` | 空库首启 seed 初始管理员 |
| `LLM_API_KEY` | LLM(DeepSeek) 服务器端密钥 |

- 经 `gcloud run deploy --set-env-vars` 注入（用 `^~^` 改分隔符，避免 DATABASE_URL 里的 `= / @ :` 被误解析）。值明文存在 Cloud Run 服务配置（自己项目内可见）——接受此代价换灵活；要硬化改用 **Secret Manager + `--set-secrets`**。
- 架构观：**对外 = 用户 auth 登录（JWT），对内 = AI key / DB 密码等服务器端密钥**，永不进前端、repo、镜像。

## 数据库迁移（容器启动时）
- 容器 CMD = `alembic upgrade head && exec uvicorn …`：每次启动先把 schema 升到最新（**幂等**：空库建表、已最新跳过），再起服务。`config.py` 与 `alembic/env.py` 都直接读 `DATABASE_URL`，socket 形原样可用。
- 第一次部署后线上自动就有：四张表 + seed 的 admin（来自 `ADMIN_*`）；剧本不 seed，由用户经编剧页创建。
- Dockerfile 须 COPY `alembic.ini` + `alembic/`。
- **并发迁移**：Cloud Run 缩到零/多实例时，首个冷启动跑迁移；同时冷启多实例有轻微竞争（alembic 幂等，风险低）。要硬化：改由 CI 部署前单跑一步，或用 Cloud Run Job / advisory lock。

## 容器要点（Dockerfile）
- 监听 `0.0.0.0:${PORT:-8080}`（Cloud Run 注入 `PORT=8080`）；**非 root** 运行。
- 多阶段：Node 只 build 前端 dist，最终镜像只含 Python + 后端 + dist；`main.py` 同源供 dist 与 `/api`。
- CMD 用 exec 形式让 uvicorn 正确收 SIGTERM。

## 怎么部署 / 触发
- **自动**：push 到 `master` → CI `test` 过 → `deploy` build+推 AR+`gcloud run deploy` → 上云。
- 取 URL：`deploy` job 日志末尾，或 `gcloud run services describe trpg --region asia-northeast1 --format='value(status.url)'`。
- 验证：`/`（简体 SPA，注册/登录后进）、`/api/health` → `{"ok":true}`、注册建号、实际玩一局（需 `LLM_API_KEY` 已注入）。

## 成本 / 拆除
- **Cloud Run 缩容到零**：无请求时不计费（比 AWS ECS 常驻更省）；`--max-instances 3` 封顶。
- **Cloud SQL 常驻计费**：db-f1-micro ~$8–10/月（免费试用额度内不花钱）。**删 Cloud Run 服务不影响 Cloud SQL**——数据活在 DB 里。彻底不用了才删：`gcloud sql instances delete trpg-pg`。
- Artifact Registry 按存储量微收（镜像小）。删服务：`gcloud run services delete trpg --region asia-northeast1`。

## 一次性 GCP 设置（复现用，Cloud Shell）
> 见提交历史 / 会话记录的完整 `gcloud` 清单：启用 API（run/artifactregistry/sqladmin/iam/iamcredentials/sts/cloudresourcemanager）→ 建 AR 仓库 → 建 Cloud SQL 实例+库+用户 → 建两个 SA + 授权 → 建 WIF 池/provider + 绑仓库 → 在 GitHub 设上面的 Variables/Secrets。

## 已知不足 / 下一步（可选硬化）
- **密钥硬化**：DB 密码/JWT/LLM key 现明文在 Cloud Run 服务配置。可改 **Secret Manager + `--set-secrets`**。
- **DB 连接 TLS**：走 Cloud SQL 连接器（socket）本身在 Google 内部加密；不额外配 sslmode。
- **JWT 仅访问令牌**：无刷新/吊销，7 天到期重登。
- **迁移并发**：多实例冷启动迁移竞争（见上）。
