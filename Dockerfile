# Multi-stage build: Node is only used to build the frontend and never ships in the final image.

# ---------- Stage 1: build the Vue frontend ----------
FROM node:20-slim AS frontend
WORKDIR /app/frontend
# Copy only the manifests first -> npm ci (cached when dependencies don't change)
COPY frontend/package*.json ./
RUN npm ci
# Then copy the sources and build /app/frontend/dist
COPY frontend/ ./
RUN npm run build

# ---------- Stage 2: runtime (Python + backend + prebuilt dist only) ----------
FROM python:3.13-slim AS runtime
WORKDIR /app

# Requirements first so code-only changes reuse the cached layer. Runtime deps only (no pytest).
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Backend + reference scenarios; the dist comes from stage 1 (main.py serves /app/frontend/dist)
COPY backend/ ./backend/
COPY scenarios/ ./scenarios/
COPY --from=frontend /app/frontend/dist ./frontend/dist
# Database migrations: `alembic upgrade head` on startup needs these (env.py reads DATABASE_URL via backend.config)
COPY alembic.ini ./
COPY alembic/ ./alembic/

# Run as non-root (least privilege)
RUN useradd -m app && chown -R app /app
USER app

# Cloud Run injects PORT (8080 by default); bind 0.0.0.0 so the container is reachable
ENV PORT=8080
EXPOSE 8080

# Health check hits the unauthenticated /api/health (slim image has no curl, so use the stdlib)
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/api/health')" || exit 1

# Run migrations, then start the server:
# - alembic upgrade head: creates tables on an empty DB and is a no-op when current (idempotent,
#   safe on every restart/redeploy). On failure (e.g. DB unreachable) the container exits and the
#   platform restarts it, with the cause in the logs.
# - exec uvicorn: uvicorn replaces the shell as PID 1 and receives SIGTERM directly (clean shutdown).
# Note: with scale-to-zero / multiple instances, concurrent cold starts race on migrations; a
# dedicated pre-deploy migration step in CI would remove that race.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
