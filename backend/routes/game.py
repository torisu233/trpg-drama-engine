"""Play routes: stateful game sessions (stored in the DB, bound to a user). Actions/reactions are streamed (NDJSON) to the frontend beat by beat.

Games are always private: list/read/delete/act by owner / admin only. Starting a game checks scenario visibility.
While streaming, each beat is saved with its own DB session (avoids lifetime issues of request dependencies inside a streaming response).
"""
import json
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session

from .. import game_store, flow, engine, agents
from .. import scenario as scen
from ..deps import get_llm
from ..db import get_db, SessionLocal
from ..auth import current_user
from ..models import Scenario
from ..models_db import Scenario as DBScenario, User

router = APIRouter(prefix="/api", tags=["game"])


def _owned_session(db: Session, gid: str, user: User):
    """Fetch your own game (admin can fetch any); otherwise 404 (doesn't leak existence). Returns (row, Session)."""
    row = game_store.load_game(db, gid)
    if not row or (row.user_id != user.id and not user.is_admin):
        raise HTTPException(404, f"Game not found: {gid}")
    return row, game_store.session_of(row)


@router.get("/games")
def list_games(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"games": game_store.list_games(db, user)}


@router.post("/game/new")
async def new_game(payload: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    sid = payload.get("scenario_id")
    if not sid:
        raise HTTPException(400, "Missing scenario_id")
    row = db.query(DBScenario).filter(DBScenario.id == int(sid), DBScenario.is_active.is_(True)).first()
    if not row:
        raise HTTPException(404, f"Scenario not found: {sid}")
    if not (user.is_admin or row.visibility == "published" or row.author_id == user.id):
        raise HTTPException(403, "Not allowed to start a game with this scenario")
    sc = Scenario(**row.content)
    s = scen.session_from_scenario(sc)
    reason = engine.validate_playable(s)     # incomplete scenario (no player / player not present / nobody present) → a clear 400, no crash or hang
    if reason:
        raise HTTPException(400, f"Scenario is incomplete and cannot be started: {reason}")
    gid = game_store.create_game(db, s, user.id, row.id)
    await flow.advance(get_llm(), s)
    game_store.save_game(db, gid, s)
    return game_store.snapshot(gid, s)


@router.get("/game/{gid}")
def get_game(gid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _, s = _owned_session(db, gid, user)
    return game_store.snapshot(gid, s)


@router.delete("/game/{gid}")
def delete_game(gid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _owned_session(db, gid, user)        # ownership check only
    game_store.delete_game(db, gid)
    return {"ok": True}


def _stream(gid: str, s, gen):
    """Wrap the flow streaming generator into NDJSON beat by beat; each beat is saved with its own DB session."""
    async def body():
        async for sess in gen:
            if not sess.in_progress:                 # preview frames (for delayed reveal) are shown immediately but never persisted, so a dropped connection leaves no half-written state
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
    return _stream(gid, s, flow.stream_action(get_llm(), s, payload.get("action", {})))


@router.post("/game/{gid}/react")
async def react(gid: str, payload: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _, s = _owned_session(db, gid, user)
    if s.ended:
        return JSONResponse(game_store.snapshot(gid, s))
    return _stream(gid, s, flow.stream_reaction(get_llm(), s, payload.get("reaction", {})))


@router.get("/game/{gid}/suggest")
async def suggest(gid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The AI proposes a "suggested move" for the player (just like an agent character would) for reference — the player still acts manually.
    Read-only: no advancing, no ledger changes, no saving; only valid at a player decision point (pending=player_action/reaction), otherwise suggestion=None.
    Reuses character_intent/reaction (the player card, controller==player, has the same full role-play fields); based on the player's fogged view, so no gm secrets leak."""
    _, s = _owned_session(db, gid, user)
    p = s.pending or {}
    if s.ended or p.get("type") not in ("player_action", "player_reaction"):
        return {"suggestion": None}
    llm = get_llm()
    pid = engine.player_id(s)
    if p.get("type") == "player_action":
        intent = await agents.character_intent(llm, s, pid)
        tid = engine.resolve_id(s, intent.target)        # name/id/None → id, for the frontend select
        return {"suggestion": {"kind": "action", "action": intent.action,
                        "target_id": tid, "target_name": (s.cards[tid].name if tid else None),
                        "covert": intent.covert}}
    reaction = await agents.character_reaction(llm, s, pid, p.get("incoming", ""))
    return {"suggestion": {"kind": "reaction", "reaction": reaction.reaction}}
