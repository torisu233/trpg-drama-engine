"""FastAPI 入口。

開發：前端 vite dev(5173) 代理到本服務(8100)。
發佈（單一服務）：先 `cd frontend && npm run build`，本服務即同時供 Vue dist 與 /api，
只要把這個埠用隧道/雲端公開即可。公開時務必設環境變數 APP_PASSWORD。

啟動：uvicorn backend.main:app --port 8100
"""
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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


@app.middleware("http")
async def password_gate(request: Request, call_next):
    """設了 APP_PASSWORD 時，/api/*（health 除外）須帶正確 X-App-Password。"""
    pw = config.APP_PASSWORD
    path = request.url.path
    if pw and path.startswith("/api/") and path != "/api/health":
        if request.headers.get("X-App-Password") != pw:
            return JSONResponse({"detail": "需要存取密碼"}, status_code=401)
    return await call_next(request)


app.include_router(scenarios.router)   # /api/scenarios*, /api/author/turn
app.include_router(game.router)        # /api/games, /api/game/*


@app.get("/api/health")
async def health():
    return {"ok": True, "model": config.GROK_MODEL}


# 發佈用：若前端已 build，直接供其 dist（前端與 API 同源，免 CORS）
_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")
