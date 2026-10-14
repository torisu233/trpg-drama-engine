"""Auth: password hashing (bcrypt), JWT issue/verify, FastAPI "current user" dependencies, admin seeding.

Design:
- Only bcrypt hashes of passwords are stored; verified at login.
- Login issues a JWT (stateless: carries user_id/username/is_admin + expiry); requests send `Authorization: Bearer`.
- `current_user` / `current_admin` are Depends dependencies; injecting them into a route requires login / admin.
"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import config
from .db import get_db, SessionLocal
from .models_db import User


# ── password hashing ──
def _pw_bytes(pw: str) -> bytes:
    return pw.encode()[:72]   # bcrypt has a hard 72-byte limit and errors beyond it; always truncate


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


# ── current-user dependencies ──
_bearer = HTTPBearer(auto_error=False)


def current_user(cred: HTTPAuthorizationCredentials = Depends(_bearer),
                 db: Session = Depends(get_db)) -> User:
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required")
    try:
        payload = jwt.decode(cred.credentials, config.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User does not exist or is deactivated")
    return user


def current_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin privileges required")
    return user


# ── seed admin (first-run bootstrap: create the initial admin from env only when the users table is empty) ──
def seed_admin() -> None:
    """On first start against a fresh, empty DB, create an admin (from env); once any user exists, never seed again."""
    if not config.ADMIN_PASSWORD:
        return
    db = SessionLocal()
    try:
        if db.query(User.id).first() is not None:   # users exist → not first run, skip
            return
        db.add(User(username=config.ADMIN_USERNAME,
                    password_hash=hash_password(config.ADMIN_PASSWORD),
                    is_admin=True))
        db.commit()
    except IntegrityError:                          # concurrent startup: another instance already seeded
        db.rollback()
    finally:
        db.close()
