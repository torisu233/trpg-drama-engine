"""pytest 共享夹具（fixtures）。

夹具 = 测试的「预备材料」：用 @pytest.fixture 定义，测试函数把夹具名写进参数，
pytest 就会自动调用并注入。好处是每个测试拿到全新、隔离的对象，互不污染。

注意：离线测试从不真的呼叫 Grok（酒馆玩家速度最高、开局即停在玩家决策点），
但 GrokClient 建构需要 GROK_API_KEY，故在此设一个 dummy，让建构不报错、也不连网。
"""
import os

os.environ.setdefault("GROK_API_KEY", "test-dummy-key")  # 必须在 import backend 之前

import pytest
from fastapi.testclient import TestClient

from backend.scene import new_tavern_session
from backend.main import app
from backend import scenario as scen


@pytest.fixture
def sess():
    """一份全新的「雨夜酒馆」Session（纯逻辑测试用），每个测试各拿一份、互相隔离。"""
    return new_tavern_session()


@pytest.fixture
def client():
    """FastAPI 测试客户端：in-process 直接打路由，不需真的起服务器，也不打 Grok。"""
    return TestClient(app)


@pytest.fixture
def tavern_id():
    """把 in-code 酒馆落地成一份临时剧本供 API 测试用；测完自动删除（yield 后即清理）。"""
    sid = "_pytest_tavern"
    scen.save_scenario(scen.scenario_from_session(new_tavern_session(), sid))
    yield sid
    (scen.SCENARIOS_DIR / f"{sid}.json").unlink(missing_ok=True)
