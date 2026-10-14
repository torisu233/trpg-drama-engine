"""Scenario routes: DB persistence + permissions (visibility/ownership) + author agent chat.

- List: published or your own; admin sees all (with author username).
- Read: published is readable by everyone; private only by the author/admin.
- Create/update/delete: logged-in users; update/delete only by the author/admin; delete = soft delete.
- Author turn: stateless (the frontend holds the draft), login required.
"""
import copy
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models import Scenario
from ..models_db import Scenario as DBScenario, User
from ..db import get_db
from ..auth import current_user
from .. import scenario as scen, agents
from ..deps import get_llm

router = APIRouter(prefix="/api", tags=["scenarios / author"])


class ScenarioSave(BaseModel):
    scenario: Scenario              # the full scenario content (stored in the content JSON column)
    visibility: str = "private"     # private | published


def _vis(v: str) -> str:
    return v if v in ("private", "published") else "private"


def _row_or_404(db: Session, sid: int) -> DBScenario:
    r = db.query(DBScenario).filter(DBScenario.id == sid, DBScenario.is_active.is_(True)).first()
    if not r:
        raise HTTPException(404, f"Scenario not found: {sid}")
    return r


@router.get("/scenarios")
def list_scenarios(user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = db.query(DBScenario).filter(DBScenario.is_active.is_(True))
    if not user.is_admin:
        q = q.filter(or_(DBScenario.visibility == "published", DBScenario.author_id == user.id))
    rows = q.order_by(DBScenario.updated_at.desc()).all()
    authors = {}
    if rows:
        ids = {r.author_id for r in rows}
        authors = {u.id: u.username for u in db.query(User).filter(User.id.in_(ids))}
    return {"scenarios": [
        {"id": r.id, "title": r.title, "visibility": r.visibility,
         "background": (((r.content or {}).get("world") or {}).get("background") or "")[:120],
         "author": authors.get(r.author_id), "is_mine": r.author_id == user.id}
        for r in rows]}


@router.get("/scenarios/{sid}")
def get_scenario(sid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = _row_or_404(db, sid)
    if not (user.is_admin or r.visibility == "published" or r.author_id == user.id):
        raise HTTPException(403, "Not allowed to view this scenario")
    return {"id": r.id, "title": r.title, "visibility": r.visibility,
            "author_id": r.author_id, "content": r.content}


@router.post("/scenarios")
def create_scenario(body: ScenarioSave, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = DBScenario(title=body.scenario.id or "Untitled scenario", author_id=user.id,
                   visibility=_vis(body.visibility), content=body.scenario.model_dump())
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"id": r.id, "title": r.title, "visibility": r.visibility}


@router.post("/scenarios/{sid}/copy")
def copy_scenario(sid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Clone a readable scenario into a private copy of "mine" (for editing on top of someone else's published scenario).

    Same read authorization as get_scenario: published / your own / admin, otherwise 403 (you can't copy a private scenario you can't see).
    """
    src = _row_or_404(db, sid)
    if not (user.is_admin or src.visibility == "published" or src.author_id == user.id):
        raise HTTPException(403, "Not allowed to copy this scenario")
    title = ((src.title or "Untitled scenario") + " (copy)")[:120]
    r = DBScenario(title=title, author_id=user.id, visibility="private",
                   content=copy.deepcopy(src.content))   # deep copy so the copy never shares references with the original
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"id": r.id, "title": r.title, "visibility": r.visibility}


@router.put("/scenarios/{sid}")
def update_scenario(sid: int, body: ScenarioSave, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = _row_or_404(db, sid)
    if not (user.is_admin or r.author_id == user.id):
        raise HTTPException(403, "Not allowed to modify this scenario")
    r.title = body.scenario.id or r.title
    r.content = body.scenario.model_dump()
    r.visibility = _vis(body.visibility)
    db.commit()
    return {"id": r.id, "title": r.title, "visibility": r.visibility}


@router.delete("/scenarios/{sid}")
def delete_scenario(sid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = _row_or_404(db, sid)
    if not (user.is_admin or r.author_id == user.id):
        raise HTTPException(403, "Not allowed to delete this scenario")
    r.is_active = False     # soft delete
    db.commit()
    return {"ok": True}


@router.post("/author/turn")
async def author_turn(payload: dict, user: User = Depends(current_user)):
    """body: {scenario, history:[{role,text}], message} → the merged full scenario + reply (stateless)."""
    sc = Scenario(**payload.get("scenario", {}))
    history = [(h.get("role", ""), h.get("text", "")) for h in payload.get("history", [])]
    message = payload.get("message", "")
    rep = await agents.author_turn(get_llm(), sc, history, message)
    updated_block = scen.apply_author_reply(sc, rep)
    return {
        "reply": rep.reply,
        "scenario": sc,
        "block": updated_block,
        "char_id": rep.char_id,
        "missing": rep.missing,
        "done": rep.done,
    }
