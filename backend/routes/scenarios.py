"""剧本路由：DB 持久化 + 权限（可见性/拥有权）+ 编剧 agent 对话。

- 列表：published 或自己的；admin 看全部（带作者 username）。
- 读：published 人人可读；private 仅作者/admin。
- 建/改/删：登录用户；改删仅作者/admin；删=软删除。
- 编剧 turn：无状态（前端持草稿），仅需登录。
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
from ..deps import get_grok

router = APIRouter(prefix="/api", tags=["scenarios / author"])


class ScenarioSave(BaseModel):
    scenario: Scenario              # 整份剧本内容（存进 content JSON 列）
    visibility: str = "private"     # private | published


def _vis(v: str) -> str:
    return v if v in ("private", "published") else "private"


def _row_or_404(db: Session, sid: int) -> DBScenario:
    r = db.query(DBScenario).filter(DBScenario.id == sid, DBScenario.is_active.is_(True)).first()
    if not r:
        raise HTTPException(404, f"找不到剧本 {sid}")
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
         "背景": (((r.content or {}).get("世界观") or {}).get("背景") or "")[:120],
         "author": authors.get(r.author_id), "is_mine": r.author_id == user.id}
        for r in rows]}


@router.get("/scenarios/{sid}")
def get_scenario(sid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = _row_or_404(db, sid)
    if not (user.is_admin or r.visibility == "published" or r.author_id == user.id):
        raise HTTPException(403, "无权查看该剧本")
    return {"id": r.id, "title": r.title, "visibility": r.visibility,
            "author_id": r.author_id, "content": r.content}


@router.post("/scenarios")
def create_scenario(body: ScenarioSave, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = DBScenario(title=body.scenario.id or "未命名剧本", author_id=user.id,
                   visibility=_vis(body.visibility), content=body.scenario.model_dump())
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"id": r.id, "title": r.title, "visibility": r.visibility}


@router.post("/scenarios/{sid}/copy")
def copy_scenario(sid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """把一份可读剧本克隆为「我的」私人副本（用于在别人发布的剧本上改）。

    读授权同 get_scenario：published / 自己的 / admin 才可读，否则 403（不可复制看不到的私人剧本）。
    """
    src = _row_or_404(db, sid)
    if not (user.is_admin or src.visibility == "published" or src.author_id == user.id):
        raise HTTPException(403, "无权复制该剧本")
    title = ((src.title or "未命名剧本") + "（副本）")[:120]
    r = DBScenario(title=title, author_id=user.id, visibility="private",
                   content=copy.deepcopy(src.content))   # 深拷贝，杜绝副本与原作共享引用
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"id": r.id, "title": r.title, "visibility": r.visibility}


@router.put("/scenarios/{sid}")
def update_scenario(sid: int, body: ScenarioSave, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = _row_or_404(db, sid)
    if not (user.is_admin or r.author_id == user.id):
        raise HTTPException(403, "无权修改该剧本")
    r.title = body.scenario.id or r.title
    r.content = body.scenario.model_dump()
    r.visibility = _vis(body.visibility)
    db.commit()
    return {"id": r.id, "title": r.title, "visibility": r.visibility}


@router.delete("/scenarios/{sid}")
def delete_scenario(sid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = _row_or_404(db, sid)
    if not (user.is_admin or r.author_id == user.id):
        raise HTTPException(403, "无权删除该剧本")
    r.is_active = False     # 软删除
    db.commit()
    return {"ok": True}


@router.post("/author/turn")
async def author_turn(payload: dict, user: User = Depends(current_user)):
    """body: {scenario, history:[{role,text}], message} → 合并后的整份剧本 + 回复（无状态）。"""
    sc = Scenario(**payload.get("scenario", {}))
    history = [(h.get("role", ""), h.get("text", "")) for h in payload.get("history", [])]
    message = payload.get("message", "")
    rep = await agents.author_turn(get_grok(), sc, history, message)
    更新区块 = scen.apply_author_reply(sc, rep)
    return {
        "reply": rep.reply,
        "scenario": sc,
        "区块": 更新区块,
        "char_id": rep.char_id,
        "missing": rep.missing,
        "done": rep.done,
    }
