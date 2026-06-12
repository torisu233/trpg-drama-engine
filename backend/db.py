"""数据库基础：engine / SessionLocal / Base / get_db 依赖。

本地与云端皆 PostgreSQL（dev/prod 一致）；靠 DATABASE_URL 切换：本地 = docker-compose 的 PG，
云端 = RDS。本地起库：`docker compose up -d --wait`。
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from . import config

# pool_pre_ping：取连接前先 ping，避开 RDS 闲置断线
engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
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
