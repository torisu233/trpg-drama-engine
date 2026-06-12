"""认证路由：注册 / 登录 / 当前用户（公开端点：register / login）。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models_db import User
from ..auth import hash_password, verify_password, create_token, current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    username: str
    password: str


def _issue(user: User) -> dict:
    return {"token": create_token(user), "username": user.username, "is_admin": user.is_admin}


@router.post("/register")
def register(body: Credentials, db: Session = Depends(get_db)):
    username = body.username.strip()
    if not (3 <= len(username) <= 32):
        raise HTTPException(400, "用户名须 3–32 字")
    if len(body.password) < 6:
        raise HTTPException(400, "密码至少 6 位")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(400, "用户名已存在")
    user = User(username=username, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return _issue(user)


@router.post("/login")
def login(body: Credentials, db: Session = Depends(get_db)):
    user = db.query(User).filter(
        User.username == body.username.strip(), User.is_active.is_(True)
    ).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    return _issue(user)


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "username": user.username, "is_admin": user.is_admin}


class ChangePassword(BaseModel):
    old_password: str
    new_password: str


@router.post("/change-password")
def change_password(body: ChangePassword, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """改密码：先验旧密码（防登录态被人改密码），再存新哈希。当前 JWT 不含密码，仍有效到期。"""
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(400, "原密码错误")
    if len(body.new_password) < 6:
        raise HTTPException(400, "新密码至少 6 位")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True}
