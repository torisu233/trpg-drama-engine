# 多阶段构建：Node 只用于 build 前端，不进最终镜像。

# ---------- 阶段 1：build Vue 前端 ----------
FROM node:20-slim AS frontend
WORKDIR /app/frontend
# 先只 copy 依赖清单 → npm ci（依赖没变时这层走缓存，build 更快）
COPY frontend/package*.json ./
RUN npm ci
# 再 copy 源码并打包，产出 /app/frontend/dist
COPY frontend/ ./
RUN npm run build

# ---------- 阶段 2：运行（只含 Python + 后端 + 已 build 的 dist）----------
FROM python:3.13-slim AS runtime
WORKDIR /app

# 先 requirements 再装：码改了但依赖没变时走缓存。只装运行期依赖（无 pytest）。
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 后端码 + 种子剧本；前端 dist 从阶段 1 拷过来（main.py 找 /app/frontend/dist）
COPY backend/ ./backend/
COPY scenarios/ ./scenarios/
COPY --from=frontend /app/frontend/dist ./frontend/dist
# 数据库迁移：启动时 alembic upgrade head 需要这两个（env.py 走 backend.config 的 DATABASE_URL）
COPY alembic.ini ./
COPY alembic/ ./alembic/

# 非 root 运行（最小权限）
RUN useradd -m app && chown -R app /app
USER app

# Cloud Run 默认从 8080 注入 PORT；监听 0.0.0.0 才能从容器外访问
ENV PORT=8080
EXPOSE 8080

# 健康检查打免密码的 /api/health（slim 镜像没 curl，用 Python 标准库）
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/api/health')" || exit 1

# 启动先跑迁移再起服务：
# - alembic upgrade head：空库自动建表、已最新则跳过（幂等，重启/重部署都安全）。
#   失败（如 DB 连不上）即退出 → Cloud Run 重启重试，日志可见原因。
# - exec uvicorn：让 uvicorn 取代 shell 成为主进程，直接收 SIGTERM（关闭干净）。
#   ${PORT} 由 Cloud Run 注入（容器端口 8080）。
# 注：Cloud Run 缩到零/多实例时，首个冷启动跑迁移（alembic 幂等）；并发多实例同时冷启有轻微竞争，将来需另设迁移闸（或改由 CI 部署前单跑一步）。
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
