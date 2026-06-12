"""FastAPI 入口。

开发：前端 vite dev(5173) 代理到本服务(8100)。
发布（单一服务）：先 `cd frontend && npm run build`，本服务即同时供 Vue dist 与 /api，
只要把这个端口用隧道/云端公开即可。公开时务必设环境变量 APP_PASSWORD。

启动：uvicorn backend.main:app --port 8100
"""
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config, deps, scenario as scen
from .routes import scenarios, game
from .routes import auth as auth_routes
from .auth import seed_admin
from .db import SessionLocal

logging.basicConfig(level=getattr(logging, config.LOG_LEVEL, logging.INFO))


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_admin()                       # 空库首次：从 env 建 admin
    db = SessionLocal()
    try:
        scen.seed_demo_scenario(db)    # 空库首次：导入 武侠001 为 admin 的已发布剧本
    finally:
        db.close()
    yield
    await deps.close_grok()


app = FastAPI(title="TRPG 原型 API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


@app.middleware("http")
async def password_gate(request: Request, call_next):
    """旧密码闸（将被 auth 取代）：设了 APP_PASSWORD 时，/api/*（health 与 auth 除外）须带 X-App-Password。"""
    pw = config.APP_PASSWORD
    path = request.url.path
    if pw and path.startswith("/api/") and path != "/api/health" and not path.startswith("/api/auth"):
        if request.headers.get("X-App-Password") != pw:
            return JSONResponse({"detail": "需要访问密码"}, status_code=401)
    return await call_next(request)


app.include_router(auth_routes.router)  # /api/auth/register, /login, /me
app.include_router(scenarios.router)    # /api/scenarios*, /api/author/turn
app.include_router(game.router)         # /api/games, /api/game/*


@app.get("/api/health")
async def health():
    return {"ok": True, "model": config.GROK_MODEL}


# 发布用：若前端已 build，直接供其 dist（前端与 API 同源，免 CORS）
_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")
