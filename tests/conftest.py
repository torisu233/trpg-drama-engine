"""Shared pytest fixtures.

A fixture is a test's "prepared material": defined with @pytest.fixture; a test function lists the fixture name
as a parameter and pytest calls it and injects the result. Each test gets a fresh, isolated object, so tests don't contaminate each other.

Two kinds of tests:
- Pure logic (test_engine/flow/scenario): use in-memory fixtures like `sess`, **no database connection**.
- Integration (test_api): hit real endpoints through TestClient (DB + JWT), using the DB/auth fixtures below.

Database strategy (dev/prod parity, tests use Postgres too):
- Connect to a **separate test database `trpg_test`**, never touching real data in the local `trpg`; conftest creates the database + tables on first run.
- Before each DB test, `TRUNCATE ... RESTART IDENTITY` empties everything: clean start, predictable auto-increment ids, no cross-contamination.
- DB fixtures are attached on demand: pure-logic tests don't depend on them → no PG connection, so they still run on their own locally.
- Locally, start PG first with `docker compose up -d --wait` (host 5433); override with TEST_DATABASE_URL.

Note: offline tests never actually call the LLM (the tavern player is fastest, so a new game stops at the player's decision point immediately),
but constructing LLMClient requires LLM_API_KEY, so a dummy is set here so construction doesn't fail and never touches the network.
"""
import os

os.environ.setdefault("LLM_API_KEY", "test-dummy-key")   # must happen before importing backend
os.environ.setdefault("ADMIN_PASSWORD", "")               # don't auto-seed admin; tests create their own data
# tests use the separate trpg_test database (default: local docker PG:5433) and never pollute real saves in the local trpg
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg2://trpg:trpg@localhost:5433/trpg_test"
)

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from fastapi.testclient import TestClient

from backend.scene import new_tavern_session
from backend.main import app
from backend import scenario as scen, config
import backend.models_db as mdb
from backend.db import engine, SessionLocal, Base
from backend.auth import create_token, hash_password


# ───────────────── pure-logic fixtures (no DB) ─────────────────
@pytest.fixture
def sess():
    """A fresh "rainy-night tavern" Session (for pure-logic tests); each test gets its own isolated copy."""
    return new_tavern_session()


# ───────────────── database infrastructure ─────────────────
@pytest.fixture(scope="session")
def _db_ready():
    """Create the test database (if missing) → drop+create all tables so the schema matches the current models. Runs once per test session."""
    url = make_url(config.DATABASE_URL)
    # connect to a database that is guaranteed to exist (trpg) to CREATE DATABASE trpg_test
    maint = create_engine(url.set(database="trpg"), isolation_level="AUTOCOMMIT")
    with maint.connect() as c:
        exists = c.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database}
        ).scalar()
        if not exists:
            c.execute(text(f'CREATE DATABASE "{url.database}"'))
    maint.dispose()

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    engine.dispose()


@pytest.fixture
def db(_db_ready):
    """A direct DB session for tests to set up data and make assertions.

    All tables are emptied first (including resetting auto-increment ids), so every DB test starts from a clean state.
    Pure-logic tests don't request this fixture → no PG connection.
    """
    with engine.begin() as c:
        tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        c.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def client():
    """FastAPI test client: hits routes in-process, no real server needed, and never calls the LLM.

    Deliberately doesn't enter the lifespan (no `with`) → seed_admin doesn't run, so tests fully control their own data.
    """
    return TestClient(app)


# ───────────────── auth fixtures ─────────────────
@pytest.fixture
def make_user(db):
    """Factory fixture: create a user and return (User, headers). headers carry a working Bearer token.

    Writes directly to the DB + issues the token with create_token (admin optional), which also exercises the real current_user decode path.
    Each fixture uses a different username to avoid unique conflicts.
    """
    def _make(username="alice", password="pw123456", admin=False):
        u = mdb.User(username=username, password_hash=hash_password(password), is_admin=admin)
        db.add(u)
        db.commit()
        db.refresh(u)
        return u, {"Authorization": f"Bearer {create_token(u)}"}
    return _make


@pytest.fixture
def user_headers(make_user):
    """Auth headers for a regular user."""
    _, h = make_user("alice")
    return h


@pytest.fixture
def admin_headers(make_user):
    """Auth headers for an admin."""
    _, h = make_user("admin", admin=True)
    return h


@pytest.fixture
def tavern_scenario(db, make_user):
    """Persist the in-code tavern as a (published) DB scenario; returns (sid, owner_headers).

    Uses the tavern session (player is fastest, the game stops at the player's decision point) → starting a game never calls the LLM, so integration tests run offline.
    """
    owner, headers = make_user("author")
    sc = scen.scenario_from_session(new_tavern_session(), "_pytest_tavern")
    row = mdb.Scenario(title=sc.id, author_id=owner.id,
                       visibility="published", content=sc.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row.id, headers
