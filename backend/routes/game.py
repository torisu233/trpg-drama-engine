"""游玩路由：有状态场次。行动/反应以串流（NDJSON）逐拍推给前端。"""
import json
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session
from .. import game_store, flow
from ..deps import get_grok
from ..db import get_db
from ..models import Scenario
from ..models_db import Scenario as DBScenario

router = APIRouter(prefix="/api", tags=["game"])


@router.get("/games")
def list_games():
    return {"games": game_store.list_games()}


@router.post("/game/new")
async def new_game(payload: dict, db: Session = Depends(get_db)):
    sid = payload.get("scenario_id")
    if not sid:
        raise HTTPException(400, "缺 scenario_id")
    row = db.query(DBScenario).filter(DBScenario.id == int(sid), DBScenario.is_active.is_(True)).first()
    if not row:
        raise HTTPException(404, f"找不到剧本 {sid}")
    sc = Scenario(**row.content)
    gid, s = game_store.create_game(sc)
    await flow.advance(get_grok(), s)
    game_store.save_game(gid, s)
    return game_store.snapshot(gid, s)


@router.get("/game/{gid}")
def get_game(gid: str):
    s = game_store.get_game(gid)
    if not s:
        raise HTTPException(404, f"找不到游戏 {gid}")
    return game_store.snapshot(gid, s)


@router.delete("/game/{gid}")
def delete_game(gid: str):
    if game_store.delete_game(gid):
        return {"ok": True}
    raise HTTPException(404, f"找不到游戏 {gid}")


def _stream(gid: str, s, gen):
    """把 flow 的串流产生器逐拍包成 NDJSON（每拍一行 snapshot），并逐拍存盘。"""
    async def body():
        async for sess in gen:
            game_store.save_game(gid, sess)
            yield json.dumps(game_store.snapshot(gid, sess), ensure_ascii=False) + "\n"
    return StreamingResponse(body(), media_type="application/x-ndjson")


@router.post("/game/{gid}/action")
async def action(gid: str, payload: dict):
    s = game_store.get_game(gid)
    if not s:
        raise HTTPException(404, f"找不到游戏 {gid}")
    if s.结束:
        return JSONResponse(game_store.snapshot(gid, s))
    return _stream(gid, s, flow.stream_action(get_grok(), s, payload.get("action", {})))


@router.post("/game/{gid}/react")
async def react(gid: str, payload: dict):
    s = game_store.get_game(gid)
    if not s:
        raise HTTPException(404, f"找不到游戏 {gid}")
    if s.结束:
        return JSONResponse(game_store.snapshot(gid, s))
    return _stream(gid, s, flow.stream_reaction(get_grok(), s, payload.get("reaction", {})))
