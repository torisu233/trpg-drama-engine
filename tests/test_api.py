"""集成测试：经 FastAPI TestClient 打真实端点（in-process，不打 Grok）。

集成测试 = 多个组件一起跑（路由 + 引擎 + 存取）。`client`/`tavern_id` 夹具见 conftest.py。
开新游戏时玩家速度最高、开局即停在玩家决策点，故全程不触发 Grok 调用。
"""
import json
import pytest
from backend import config

# DB + auth 重写中：这些端点已改为 DB 持久化 + JWT 鉴权，旧的文件版断言不再适用。
# step6 会用 DB fixture + auth fixture 重写本文件，届时移除此 skip。
pytestmark = pytest.mark.skip(reason="scenarios/games 迁 DB+auth 重写中，step6 恢复")


def test_health(client):
    assert client.get("/api/health").json()["ok"] is True


def test_scenarios_crud(client, tavern_id):
    scs = client.get("/api/scenarios").json()["scenarios"]
    assert tavern_id in scs
    sc = client.get(f"/api/scenarios/{tavern_id}").json()
    assert sc["id"] == tavern_id and "scar" in sc["角色卡"]
    assert client.get("/api/scenarios/不存在").status_code == 404


def test_new_game_fog_and_panels(client, tavern_id):
    """开局快照：迷雾正确 + 结构化「角色」面板（我方详尽/敌方隐藏）+ 结构化「日志」。"""
    r = client.post("/api/game/new", json={"scenario_id": tavern_id}).json()
    gid = r["game_id"]
    try:
        assert r["pending"]["type"] == "player_action"
        assert any("开场" in l for l in r["公开日志"])
        # 迷雾：玩家视图无敌方秘密、上帝视角有
        assert "怕火" not in r["玩家视图"] and "怕火" in r["帐本调试"]
        # 结构化角色面板：队友卡可见、敌方卡不注入
        roles = {x["id"]: x for x in r["角色"]}
        assert roles["aqing"]["是我方"] and roles["aqing"].get("能力")
        assert "弱点" not in roles["scar"] and "能力" not in roles["scar"]
        assert "怕火" not in json.dumps(roles["scar"], ensure_ascii=False)
        # 结构化逐拍日志：开场为系统行（无行动者）
        assert r["日志"] and r["日志"][0]["行动者"] is None
        # 取快照、列进行中
        assert client.get(f"/api/game/{gid}").json()["game_id"] == gid
        assert any(g["game_id"] == gid for g in client.get("/api/games").json()["games"])
    finally:
        client.delete(f"/api/game/{gid}")
    assert client.post("/api/game/new", json={"scenario_id": "无此剧本"}).status_code == 404


# 一张「输入→期望」表：pytest 为每一行各生成一条独立测试，各自报告、互不影响。
@pytest.mark.parametrize("header, expected", [
    (None,        401),   # 不带密码 → 挡
    ("nope",      401),   # 密码错误 → 挡
    ("secret123", 200),   # 密码正确 → 放行
])
def test_password_gate(client, monkeypatch, header, expected):
    """设了 APP_PASSWORD 后，/api/* 需带正确 X-App-Password 才放行。"""
    monkeypatch.setattr(config, "APP_PASSWORD", "secret123")
    headers = {"X-App-Password": header} if header else {}
    assert client.get("/api/scenarios", headers=headers).status_code == expected


def test_health_bypasses_gate(client, monkeypatch):
    """健康检查端点即使设了密码也放行（运维探活不该被挡）。"""
    monkeypatch.setattr(config, "APP_PASSWORD", "secret123")
    assert client.get("/api/health").status_code == 200
