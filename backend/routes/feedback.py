"""反馈聊天：普通用户与 admin 来回对话。

- 用户端（current_user）：只能读/写自己那条会话线。
- admin 端（current_admin）：看所有会话列表、读/回某用户的会话；非 admin 一律 403。
权限全在后端把关，前端按角色显示哪个入口只是 UX。
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models_db import User, FeedbackMessage
from ..auth import current_user, current_admin

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


class MessageIn(BaseModel):
    body: str


def _msg(m: FeedbackMessage) -> dict:
    return {
        "id": m.id,
        "sender_is_admin": m.sender_is_admin,
        "body": m.body,
        "created_at": m.created_at.isoformat(),
    }


def _thread(db: Session, uid: int) -> list:
    rows = (db.query(FeedbackMessage)
            .filter(FeedbackMessage.thread_user_id == uid)
            .order_by(FeedbackMessage.created_at.asc()).all())
    return [_msg(m) for m in rows]


# ── 用户端（自己那条线）──
@router.get("")
def my_thread(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"messages": _thread(db, user.id)}


@router.post("")
def my_send(body: MessageIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    text = body.body.strip()
    if not text:
        raise HTTPException(400, "内容不能为空")
    db.add(FeedbackMessage(thread_user_id=user.id, sender_is_admin=False, body=text, is_read=False))
    db.commit()
    return {"ok": True}


# ── admin 端（所有会话）──
@router.get("/threads")
def threads(admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """会话列表：每个用户最新一条 + 未读数（该用户发的、admin 未读的）。按最新活动倒序。"""
    agg = {}
    for m in db.query(FeedbackMessage).order_by(FeedbackMessage.created_at.asc()).all():
        t = agg.setdefault(m.thread_user_id, {"unread": 0, "last": "", "last_at": None})
        t["last"] = m.body
        t["last_at"] = m.created_at
        if not m.sender_is_admin and not m.is_read:
            t["unread"] += 1
    if not agg:
        return {"threads": []}
    names = {u.id: u.username for u in db.query(User).filter(User.id.in_(agg.keys()))}
    out = [{"user_id": uid, "username": names.get(uid, f"#{uid}"),
            "last": t["last"], "last_at": t["last_at"].isoformat() if t["last_at"] else None,
            "unread": t["unread"]}
           for uid, t in agg.items()]
    out.sort(key=lambda x: x["last_at"] or "", reverse=True)
    return {"threads": out}


@router.get("/{user_id}")
def admin_thread(user_id: int, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """读某用户的会话，并把其未读消息标记为已读（admin 打开即已读）。"""
    msgs = _thread(db, user_id)
    db.query(FeedbackMessage).filter(
        FeedbackMessage.thread_user_id == user_id,
        FeedbackMessage.sender_is_admin.is_(False),
        FeedbackMessage.is_read.is_(False),
    ).update({"is_read": True})
    db.commit()
    u = db.get(User, user_id)
    return {"user_id": user_id, "username": u.username if u else f"#{user_id}", "messages": msgs}


@router.post("/{user_id}")
def admin_reply(user_id: int, body: MessageIn, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    text = body.body.strip()
    if not text:
        raise HTTPException(400, "内容不能为空")
    if not db.get(User, user_id):
        raise HTTPException(404, "用户不存在")
    db.add(FeedbackMessage(thread_user_id=user_id, sender_is_admin=True, body=text, is_read=True))
    db.commit()
    return {"ok": True}
