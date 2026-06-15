"""FastAPI 入口。

开发：前端 vite dev(5173) 代理到本服务(8100)；两者分开跑。
云端：Docker 镜像里前端已 build 成静态 dist，本服务同时供 dist 与 /api（同源），
部署在 AWS ECS Express（见 docs/部署.md）。

访问控制：靠用户 auth（注册/登录 + JWT Bearer），见 routes/auth.py。
启动：uvicorn backend.main:app --port 8100
"""
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config, deps, scenario as scen
from .routes import scenarios, game, feedback
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


app.include_router(auth_routes.router)  # /api/auth/register, /login, /me
app.include_router(scenarios.router)    # /api/scenarios*, /api/author/turn
app.include_router(game.router)         # /api/games, /api/game/*
app.include_router(feedback.router)     # /api/feedback*（用户+admin 反馈聊天）


@app.get("/api/health")
async def health():
    return {"ok": True, "model": config.LLM_MODEL}


# 发布用：若前端已 build，直接供其 dist（前端与 API 同源，免 CORS）
_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")
