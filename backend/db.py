"""Database basics: engine / SessionLocal / Base / get_db dependency.

PostgreSQL both locally and in the cloud (dev/prod parity), switched via DATABASE_URL: local = the docker-compose PG,
cloud = the managed instance. Start the local DB with `docker compose up -d --wait`.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from . import config

# pool_pre_ping: ping before handing out a connection, to survive idle disconnects from the managed DB
engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Base class for all ORM models (SQLAlchemy 2.0 declarative)."""
    pass


def get_db():
    """FastAPI dependency: open one DB session per request and close it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
