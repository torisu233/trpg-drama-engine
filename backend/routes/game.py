"""遊玩路由：有狀態場次（載入劇本→Session），每次行動後存檔。"""
from fastapi import APIRouter, HTTPException
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
    await flow.advance(get_grok(), s)        # 推進到第一個玩家決策點
    game_store.save_game(gid, s)
    return game_store.snapshot(gid, s)


@router.get("/game/{gid}")
def get_game(gid: str):
    s = game_store.get_game(gid)
    if not s:
        raise HTTPException(404, f"找不到遊戲 {gid}")
    return game_store.snapshot(gid, s)


@router.post("/game/{gid}/action")
async def action(gid: str, payload: dict):
    s = game_store.get_game(gid)
    if not s:
        raise HTTPException(404, f"找不到遊戲 {gid}")
    if not s.結束:
        await flow.submit_player_action(get_grok(), s, payload.get("action", {}))
        game_store.save_game(gid, s)
    return game_store.snapshot(gid, s)


@router.post("/game/{gid}/react")
async def react(gid: str, payload: dict):
    s = game_store.get_game(gid)
    if not s:
        raise HTTPException(404, f"找不到遊戲 {gid}")
    if not s.結束:
        await flow.submit_player_reaction(get_grok(), s, payload.get("reaction", {}))
        game_store.save_game(gid, s)
    return game_store.snapshot(gid, s)
