"""遊玩路由：有狀態場次。行動/反應以串流（NDJSON）逐拍推給前端。"""
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from .. import game_store, flow
from ..deps import get_grok

router = APIRouter(prefix="/api", tags=["game"])


@router.get("/games")
def list_games():
    return {"games": game_store.list_games()}


@router.post("/game/new")
async def new_game(payload: dict):
    sid = payload.get("scenario_id")
    if not sid:
        raise HTTPException(400, "缺 scenario_id")
    try:
        gid, s = game_store.create_game(sid)
    except FileNotFoundError:
        raise HTTPException(404, f"找不到劇本 {sid}")
    await flow.advance(get_grok(), s)
    game_store.save_game(gid, s)
    return game_store.snapshot(gid, s)


@router.get("/game/{gid}")
def get_game(gid: str):
    s = game_store.get_game(gid)
    if not s:
        raise HTTPException(404, f"找不到遊戲 {gid}")
    return game_store.snapshot(gid, s)


@router.delete("/game/{gid}")
def delete_game(gid: str):
    if game_store.delete_game(gid):
        return {"ok": True}
    raise HTTPException(404, f"找不到遊戲 {gid}")


def _stream(gid: str, s, gen):
    """把 flow 的串流產生器逐拍包成 NDJSON（每拍一行 snapshot），並逐拍存檔。"""
    async def body():
        async for sess in gen:
            game_store.save_game(gid, sess)
            yield json.dumps(game_store.snapshot(gid, sess), ensure_ascii=False) + "\n"
    return StreamingResponse(body(), media_type="application/x-ndjson")


@router.post("/game/{gid}/action")
async def action(gid: str, payload: dict):
    s = game_store.get_game(gid)
    if not s:
        raise HTTPException(404, f"找不到遊戲 {gid}")
    if s.結束:
        return JSONResponse(game_store.snapshot(gid, s))
    return _stream(gid, s, flow.stream_action(get_grok(), s, payload.get("action", {})))


@router.post("/game/{gid}/react")
async def react(gid: str, payload: dict):
    s = game_store.get_game(gid)
    if not s:
        raise HTTPException(404, f"找不到遊戲 {gid}")
    if s.結束:
        return JSONResponse(game_store.snapshot(gid, s))
    return _stream(gid, s, flow.stream_reaction(get_grok(), s, payload.get("reaction", {})))
