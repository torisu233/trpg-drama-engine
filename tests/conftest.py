"""pytest 共享夹具（fixtures）。

夹具 = 测试的「预备材料」：用 @pytest.fixture 定义，测试函数把夹具名写进参数，
pytest 就会自动调用并注入。好处是每个测试拿到全新、隔离的对象，互不污染。

两类测试：
- 纯逻辑（test_engine/flow/scenario）：用 `sess` 等内存夹具，**不连数据库**。
- 集成（test_api）：经 TestClient 打真实端点（DB + JWT），用下面的 DB/auth 夹具。

数据库策略（dev/prod 一致，测试也用 Postgres）：
- 连一个**独立测试库 `trpg_test`**，绝不碰本地 `trpg` 的真实数据；conftest 首次自动建库 + 建表。
- 每个 DB 测试前 `TRUNCATE ... RESTART IDENTITY` 清空，干净起点、自增 id 可预测、互不污染。
- DB 夹具按需挂载：纯逻辑测试不依赖它们 → 不连 PG，本地照样能单独跑。
- 本地需先 `docker compose up -d --wait` 起 PG（host 5433）；可用 TEST_DATABASE_URL 覆盖。

注意：离线测试从不真的呼叫 Grok（酒馆玩家速度最高、开局即停在玩家决策点），
但 GrokClient 建构需要 LLM_API_KEY，故在此设一个 dummy，让建构不报错、也不连网。
"""
import os

os.environ.setdefault("LLM_API_KEY", "test-dummy-key")   # 必须在 import backend 之前
os.environ.setdefault("ADMIN_PASSWORD", "")               # 不自动 seed admin，测试自造数据
# 测试连独立库 trpg_test（默认本地 docker PG:5433），绝不污染本地 trpg 的真实存档
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


# ───────────────── 纯逻辑夹具（不连 DB）─────────────────
@pytest.fixture
def sess():
    """一份全新的「雨夜酒馆」Session（纯逻辑测试用），每个测试各拿一份、互相隔离。"""
    return new_tavern_session()


# ───────────────── 数据库基础设施 ─────────────────
@pytest.fixture(scope="session")
def _db_ready():
    """建测试库（若无）→ drop+create 全表，保证 schema 与当前模型一致。整轮测试只跑一次。"""
    url = make_url(config.DATABASE_URL)
    # 连一个一定存在的库（trpg）来 CREATE DATABASE trpg_test
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
    """直连 DB 的 session，供测试做前置数据与断言。

    取用前先清空所有表（含重置自增 id），所以每个用到 DB 的测试都从干净状态起步。
    纯逻辑测试不请求这个夹具 → 不连 PG。
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
    """FastAPI 测试客户端：in-process 直接打路由，不需真的起服务器，也不打 Grok。

    刻意不进入 lifespan（不 `with`）→ 不触发 seed_admin，测试完全掌控自己的数据。
    """
    return TestClient(app)


# ───────────────── auth 夹具 ─────────────────
@pytest.fixture
def make_user(db):
    """工厂夹具：建用户并返回 (User, headers)。headers 带可用的 Bearer token。

    直接造库 + 用 create_token 发 token（可设 admin），顺带真实走过 current_user 解码路径。
    各夹具用不同 username，避免 unique 冲突。
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
    """一个普通用户的鉴权头。"""
    _, h = make_user("alice")
    return h


@pytest.fixture
def admin_headers(make_user):
    """一个管理员的鉴权头。"""
    _, h = make_user("admin", admin=True)
    return h


@pytest.fixture
def tavern_scenario(db, make_user):
    """把 in-code 酒馆落地成一份 DB 剧本（已发布），返回 (sid, owner_headers)。

    用酒馆 session（玩家速度最高、开局停在玩家决策点）→ 开局不触发 Grok，集成测试可离线跑。
    """
    owner, headers = make_user("author")
    sc = scen.scenario_from_session(new_tavern_session(), "_pytest_tavern")
    row = mdb.Scenario(title=sc.id, author_id=owner.id,
                       visibility="published", content=sc.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row.id, headers
