"""SQLAlchemy ORM 模型（DB 表）。SQLAlchemy 2.0 风格（Mapped/mapped_column）。

约定：DB 列名用英文（驱动/工具/Alembic 友好）；中文内容（Scenario/Session）整份存在
content/state 的 JSON 列里。删除一律走软删除 `is_active`。
"""
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)      # 软删除
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Scenario(Base):
    __tablename__ = "scenarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    visibility: Mapped[str] = mapped_column(String(16), default="private")  # private | published
    content: Mapped[dict] = mapped_column(JSON)                          # 整个 Scenario dump
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Game(Base):
    """游玩历史，永远私人（仅 user_id 本人 / admin 可见）。"""
    __tablename__ = "games"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)        # uuid hex
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    scenario_id: Mapped[int | None] = mapped_column(ForeignKey("scenarios.id"), nullable=True)
    state: Mapped[dict] = mapped_column(JSON)                            # 整个 Session dump
    turn_count: Mapped[int] = mapped_column(Integer, default=0)          # 列表显示用（冗余）
    ended: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
