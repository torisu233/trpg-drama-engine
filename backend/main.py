"""FastAPI 入口（純 API；前端改由 Vite/Vue 另起並跨域呼叫）。

啟動：
    uvicorn backend.main:app --reload --port 8100
文件：http://127.0.0.1:8100/docs
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config, deps
from .routes import scenarios, game

logging.basicConfig(level=getattr(logging, config.LOG_LEVEL, logging.INFO))


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await deps.close_grok()


app = FastAPI(title="TRPG 原型 API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)
app.include_router(scenarios.router)   # /api/scenarios*, /api/author/turn
app.include_router(game.router)        # /api/games, /api/game/*


@app.get("/api/health")
async def health():
    return {"ok": True, "model": config.GROK_MODEL}
