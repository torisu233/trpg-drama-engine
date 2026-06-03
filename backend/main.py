"""FastAPI 入口（原型：單一全域 session，單人遊玩）。

啟動：
    uvicorn backend.main:app --reload --port 8100
前端：另開 http://127.0.0.1:8090 （見 frontend/）
"""
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config, engine, scene as scene_mod, flow
from .grok_client import GrokClient

logging.basicConfig(level=getattr(logging, config.LOG_LEVEL, logging.INFO))

STATE = {"session": None, "grok": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    STATE["grok"] = GrokClient()
    yield
    if STATE["grok"]:
        await STATE["grok"].close()


app = FastAPI(title="TRPG 原型", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def snapshot() -> dict:
    s = STATE["session"]
    if not s:
        return {"started": False}
    return {
        "started": True,
        "回合數": s.回合數,
        "結束": s.結束,
        "pending": s.pending,
        "公開日誌": s.公開日誌,
        "玩家視圖": engine.build_view(s, "player"),
        "帳本除錯": engine.ground_truth(s),  # 開發用：顯示含 gm 秘密的全貌
    }


@app.get("/api/health")
async def health():
    return {"ok": True, "model": config.GROK_MODEL}


@app.post("/api/start")
async def start():
    STATE["session"] = scene_mod.new_tavern_session()
    await flow.advance(STATE["grok"], STATE["session"])
    return snapshot()


@app.post("/api/action")
async def action(payload: dict):
    s = STATE["session"]
    if not s or s.結束:
        return snapshot()
    act = payload.get("action", {})
    await flow.submit_player_action(STATE["grok"], s, act)
    return snapshot()


@app.post("/api/react")
async def react(payload: dict):
    s = STATE["session"]
    if not s or s.結束:
        return snapshot()
    rea = payload.get("reaction", {})
    await flow.submit_player_reaction(STATE["grok"], s, rea)
    return snapshot()


@app.get("/api/state")
async def state():
    return snapshot()


# 掛載前端靜態檔（可選；也可另起 http.server）
_frontend = Path(__file__).resolve().parent.parent / "frontend"
if _frontend.exists():
    app.mount("/", StaticFiles(directory=str(_frontend), html=True), name="frontend")
