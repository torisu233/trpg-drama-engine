"""认证：密码哈希(bcrypt)、JWT 签发/校验、FastAPI「当前用户」依赖、seed admin。

设计：
- 密码只存 bcrypt 哈希；登录时 verify。
- 登录发 JWT（无状态：内含 user_id/username/is_admin + 过期），请求带 `Authorization: Bearer`。
- `current_user` / `current_admin` 是 Depends 依赖，注入路由即要求登录 / 管理员。
"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from . import config
from .db import get_db, SessionLocal
from .models_db import User


# ── 密码哈希 ──
def _pw_bytes(pw: str) -> bytes:
    return pw.encode()[:72]   # bcrypt 硬限制 72 字节，超过会报错；统一截断


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(_pw_bytes(pw), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(_pw_bytes(pw), hashed.encode())


# ── JWT ──
def create_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "is_admin": user.is_admin,
        "iat": now,
        "exp": now + timedelta(days=config.JWT_TTL_DAYS),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")


# ── 当前用户依赖 ──
_bearer = HTTPBearer(auto_error=False)


def current_user(cred: HTTPAuthorizationCredentials = Depends(_bearer),
                 db: Session = Depends(get_db)) -> User:
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "需要登录")
    try:
        payload = jwt.decode(cred.credentials, config.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token 无效或已过期")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在或已停用")
    return user


def current_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")
    return user


# ── seed admin（开机幂等；仅当设了 ADMIN_PASSWORD）──
def seed_admin() -> None:
    if not config.ADMIN_PASSWORD:
        return
    db = SessionLocal()
    try:
        if db.query(User).filter(User.username == config.ADMIN_USERNAME).first():
            return
        db.add(User(username=config.ADMIN_USERNAME,
                    password_hash=hash_password(config.ADMIN_PASSWORD),
                    is_admin=True))
        db.commit()
    finally:
        db.close()
