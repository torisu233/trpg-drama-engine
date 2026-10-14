"""SQLAlchemy ORM models (DB tables). SQLAlchemy 2.0 style (Mapped/mapped_column).

Convention: relational columns hold metadata only; the full game content (Scenario/Session) is stored as a whole
in the content/state JSON columns. Deletion is always a soft delete via `is_active`.
"""
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, JSON, Text
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
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)      # soft delete
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Scenario(Base):
    __tablename__ = "scenarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    visibility: Mapped[str] = mapped_column(String(16), default="private")  # private | published
    content: Mapped[dict] = mapped_column(JSON)                          # the whole Scenario dump
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Game(Base):
    """Play history, always private (visible only to the owning user_id / admin)."""
    __tablename__ = "games"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)        # uuid hex
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    scenario_id: Mapped[int | None] = mapped_column(ForeignKey("scenarios.id"), nullable=True)
    state: Mapped[dict] = mapped_column(JSON)                            # the whole Session dump
    turn_count: Mapped[int] = mapped_column(Integer, default=0)          # for list display (redundant)
    ended: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class FeedbackMessage(Base):
    """Feedback chat: one thread per regular user, always with "admin".

    thread_user_id = which regular user the thread belongs to; sender_is_admin tells who sent it;
    is_read = whether admin has read the user's message (drives the admin unread badge; admin's own messages are always read).
    """
    __tablename__ = "feedback_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    thread_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    sender_is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    body: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
