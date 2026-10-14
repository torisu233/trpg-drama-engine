"""游玩路由：有状态场次（存 DB，绑 user）。action/反应以串流（NDJSON）逐拍推给前端。

游戏永远私人：列/读/删/行动仅本人 / admin。开局检查剧本可见性。
串流时每拍用独立 session 存回 DB（避开请求依赖在流式响应里的生命周期问题）。
"""
import json
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session

from .. import game_store, flow, engine, agents
from .. import scenario as scen
from ..deps import get_grok
from ..db import get_db, SessionLocal
from ..auth import current_user
from ..models import Scenario
from ..models_db import Scenario as DBScenario, User

router = APIRouter(prefix="/api", tags=["game"])


def _owned_session(db: Session, gid: str, user: User):
    """取自己的游戏（admin 可取任意）；否则 404（不泄露存在性）。返回 (row, Session)。"""
    row = game_store.load_game(db, gid)
    if not row or (row.user_id != user.id and not user.is_admin):
        raise HTTPException(404, f"找不到游戏 {gid}")
    return row, game_store.session_of(row)


@router.get("/games")
def list_games(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"games": game_store.list_games(db, user)}


@router.post("/game/new")
async def new_game(payload: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    sid = payload.get("scenario_id")
    if not sid:
        raise HTTPException(400, "缺 scenario_id")
    row = db.query(DBScenario).filter(DBScenario.id == int(sid), DBScenario.is_active.is_(True)).first()
    if not row:
        raise HTTPException(404, f"找不到剧本 {sid}")
    if not (user.is_admin or row.visibility == "published" or row.author_id == user.id):
        raise HTTPException(403, "无权用该剧本开局")
    sc = Scenario(**row.content)
    s = scen.session_from_scenario(sc)
    reason = engine.validate_playable(s)     # 不完整剧本（无玩家/玩家不在场/无在场角色）→ 清晰 400，不崩不挂
    if reason:
        raise HTTPException(400, f"剧本不完整，无法开局：{reason}")
    gid = game_store.create_game(db, s, user.id, row.id)
    await flow.advance(get_grok(), s)
    game_store.save_game(db, gid, s)
    return game_store.snapshot(gid, s)


@router.get("/game/{gid}")
def get_game(gid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _, s = _owned_session(db, gid, user)
    return game_store.snapshot(gid, s)


@router.delete("/game/{gid}")
def delete_game(gid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _owned_session(db, gid, user)        # 仅校验拥有权
    game_store.delete_game(db, gid)
    return {"ok": True}


def _stream(gid: str, s, gen):
    """把 flow 的串流产生器逐拍包成 NDJSON；每拍用独立 DB session 存回。"""
    async def body():
        async for sess in gen:
            if not sess.in_progress:                 # 预告帧（延迟遮盖用）只即时显示、不入库，断线不留半截脏状态
                db = SessionLocal()
                try:
                    game_store.save_game(db, gid, sess)
                finally:
                    db.close()
            yield json.dumps(game_store.snapshot(gid, sess), ensure_ascii=False) + "\n"
    return StreamingResponse(body(), media_type="application/x-ndjson")


@router.post("/game/{gid}/action")
async def action(gid: str, payload: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _, s = _owned_session(db, gid, user)
    if s.ended:
        return JSONResponse(game_store.snapshot(gid, s))
    return _stream(gid, s, flow.stream_action(get_grok(), s, payload.get("action", {})))


@router.post("/game/{gid}/react")
async def react(gid: str, payload: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _, s = _owned_session(db, gid, user)
    if s.ended:
        return JSONResponse(game_store.snapshot(gid, s))
    return _stream(gid, s, flow.stream_reaction(get_grok(), s, payload.get("reaction", {})))


@router.get("/game/{gid}/suggest")
async def suggest(gid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """AI 替玩家出一个「参考行为」（如同 agent 角色那样），供玩家参考——玩家仍手动行动。
    只读：不推进、不落账、不存档；仅在玩家决策点(pending=player_action/reaction)有效，否则建议=None。
    复用 character_intent/reaction（玩家卡 controller==player 同有完整演戏字段）；基于玩家视野(雾)不漏 gm 秘密。"""
    _, s = _owned_session(db, gid, user)
    p = s.pending or {}
    if s.ended or p.get("type") not in ("player_action", "player_reaction"):
        return {"suggestion": None}
    grok = get_grok()
    pid = engine.player_id(s)
    if p.get("type") == "player_action":
        intent = await agents.character_intent(grok, s, pid)
        tid = engine.resolve_id(s, intent.target)        # name/id/None → id，给前端 select 用
        return {"suggestion": {"kind": "action", "action": intent.action,
                        "target_id": tid, "target_name": (s.cards[tid].name if tid else None),
                        "covert": intent.covert}}
    reaction = await agents.character_reaction(grok, s, pid, p.get("incoming", ""))
    return {"suggestion": {"kind": "reaction", "reaction": reaction.reaction}}
