"""数据库基础：engine / SessionLocal / Base / get_db 依赖。

本地默认 SQLite（零设置）；云端 DATABASE_URL=postgresql+psycopg2://... 指向 RDS。同一套代码。
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from . import config

# SQLite 在多线程（FastAPI）下需 check_same_thread=False；Postgres 不需要
_sqlite = config.DATABASE_URL.startswith("sqlite")
_connect_args = {"check_same_thread": False} if _sqlite else {}

# pool_pre_ping：取连接前先 ping，避开 RDS 闲置断线
engine = create_engine(config.DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类（SQLAlchemy 2.0 声明式）。"""
    pass


def get_db():
    """FastAPI 依赖：每个请求开一个 DB session，用完即关。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
