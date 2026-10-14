"""FastAPI entry point.

Development: the frontend vite dev server (5173) proxies to this service (8100); the two run separately.
Cloud: the Docker image contains the frontend pre-built as a static dist; this service serves both dist and /api (same origin),
deployed on GCP Cloud Run (see docs/deployment.md).

Access control: user auth (register/login + JWT Bearer), see routes/auth.py.
Run: uvicorn backend.main:app --port 8100
"""
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config, deps
from .routes import scenarios, game, feedback
from .routes import auth as auth_routes
from .auth import seed_admin

logging.basicConfig(level=getattr(logging, config.LOG_LEVEL, logging.INFO))


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_admin()                       # first run on an empty DB: create the admin from env (scenarios are not seeded; users create them)
    yield
    await deps.close_llm()


app = FastAPI(title="TRPG Drama Engine API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


app.include_router(auth_routes.router)  # /api/auth/register, /login, /me
app.include_router(scenarios.router)    # /api/scenarios*, /api/author/turn
app.include_router(game.router)         # /api/games, /api/game/*
app.include_router(feedback.router)     # /api/feedback* (user + admin feedback chat)


@app.get("/api/health")
async def health():
    return {"ok": True, "model": config.LLM_MODEL}


# production: if the frontend is built, serve its dist directly (frontend and API share an origin, no CORS needed)
_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")
