"""游玩路由：有状态场次（存 DB，绑 user）。行动/反应以串流（NDJSON）逐拍推给前端。

游戏永远私人：列/读/删/行动仅本人 / admin。开局检查剧本可见性。
串流时每拍用独立 session 存回 DB（避开请求依赖在流式响应里的生命周期问题）。
"""
import json
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session

from .. import game_store, flow
from ..deps import get_grok
from ..db import get_db, SessionLocal
from ..auth import current_user
from ..models import Scenario
from ..models_db import Scenario as DBScenario, Game, User

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
    gid, s = game_store.create_game(db, sc, user.id, row.id)
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
            if not sess.进行中:                 # 预告帧（延迟遮盖用）只即时显示、不入库，断线不留半截脏状态
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
    if s.结束:
        return JSONResponse(game_store.snapshot(gid, s))
    return _stream(gid, s, flow.stream_action(get_grok(), s, payload.get("action", {})))


@router.post("/game/{gid}/react")
async def react(gid: str, payload: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _, s = _owned_session(db, gid, user)
    if s.结束:
        return JSONResponse(game_store.snapshot(gid, s))
    return _stream(gid, s, flow.stream_reaction(get_grok(), s, payload.get("reaction", {})))
