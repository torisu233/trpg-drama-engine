"""集成测试：经 FastAPI TestClient 打真实端点（in-process，不打 Grok）。

集成测试 = 多个组件一起跑（路由 + 鉴权 + 引擎 + DB 存取）。夹具见 conftest.py：
`client`（TestClient）/ `db`（直连 session，取用前清库）/ `make_user`·`user_headers`·
`admin_headers`（造用户发 JWT）/ `tavern_scenario`（落地一份已发布酒馆剧本）。

端点现为 DB 持久化 + JWT 鉴权，所以这里重点覆盖**授权边界**（401 未登录 / 403 无权 /
404 不泄露存在性）与**可见性·拥有权**，外加开局快照的迷雾/面板/日志结构。
开新游戏时玩家速度最高、开局即停在玩家决策点，故全程不触发 Grok 调用。
"""
import json
import pytest

from backend import scenario as scen
from backend.scene import new_tavern_session


def _scenario_body(name="测试剧本", visibility="private"):
    """构造一份合法的 ScenarioSave 请求体（用酒馆数据，保证通过 Scenario 校验）。"""
    sc = scen.scenario_from_session(new_tavern_session(), name)
    return {"scenario": sc.model_dump(mode="json"), "visibility": visibility}


# ───────────────── 健康检查（无需鉴权）─────────────────
def test_health(client):
    assert client.get("/api/health").json()["ok"] is True


# ───────────────── 认证：注册 / 登录 / me ─────────────────
def test_register_login_me(client, db):
    r = client.post("/api/auth/register", json={"username": "bob", "password": "pw123456"})
    assert r.status_code == 200
    token = r.json()["token"]
    assert r.json()["username"] == "bob" and r.json()["is_admin"] is False

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["username"] == "bob"

    lg = client.post("/api/auth/login", json={"username": "bob", "password": "pw123456"})
    assert lg.status_code == 200 and lg.json()["token"]


@pytest.mark.parametrize("username, password, why", [
    ("ab",                "pw123456", "用户名太短"),
    ("x" * 33,            "pw123456", "用户名太长"),
    ("goodname",          "12345",    "密码太短"),
], ids=["短名", "长名", "短密码"])
def test_register_validation(client, db, username, password, why):
    assert client.post("/api/auth/register",
                       json={"username": username, "password": password}).status_code == 400


def test_register_duplicate(client, make_user):
    make_user("alice")        # 已存在
    assert client.post("/api/auth/register",
                       json={"username": "alice", "password": "pw123456"}).status_code == 400


def test_login_wrong_password(client, make_user):
    make_user("alice", password="rightpass")
    assert client.post("/api/auth/login",
                       json={"username": "alice", "password": "wrongpass"}).status_code == 401


@pytest.mark.parametrize("headers, expected", [
    (None,                                401),   # 不带 token → 挡
    ({"Authorization": "Bearer rubbish"}, 401),   # token 无效 → 挡
], ids=["无token", "坏token"])
def test_me_requires_auth(client, headers, expected):
    assert client.get("/api/auth/me", headers=headers or {}).status_code == expected


# ───────────────── 剧本：鉴权 + CRUD + 可见性 + 拥有权 ─────────────────
def test_scenarios_require_auth(client):
    assert client.get("/api/scenarios").status_code == 401


def test_scenario_crud(client, user_headers):
    # 建
    cr = client.post("/api/scenarios", json=_scenario_body("我的剧本"), headers=user_headers)
    assert cr.status_code == 200
    sid = cr.json()["id"]
    assert isinstance(sid, int)

    # 列：出现在自己的列表，且标记 is_mine
    lst = client.get("/api/scenarios", headers=user_headers).json()["scenarios"]
    mine = next(s for s in lst if s["id"] == sid)
    assert mine["is_mine"] and mine["title"] == "我的剧本"

    # 读：拿得到 content
    got = client.get(f"/api/scenarios/{sid}", headers=user_headers).json()
    assert got["id"] == sid and "scar" in got["content"]["角色卡"]

    # 改：标题 + 可见性
    upd = client.put(f"/api/scenarios/{sid}",
                     json=_scenario_body("改名了", visibility="published"), headers=user_headers)
    assert upd.status_code == 200 and upd.json()["visibility"] == "published"
    assert client.get(f"/api/scenarios/{sid}", headers=user_headers).json()["title"] == "改名了"

    # 删（软删）：列表消失、再读 404
    assert client.delete(f"/api/scenarios/{sid}", headers=user_headers).status_code == 200
    assert all(s["id"] != sid for s in client.get("/api/scenarios", headers=user_headers).json()["scenarios"])
    assert client.get(f"/api/scenarios/{sid}", headers=user_headers).status_code == 404


def test_scenario_visibility_private_hidden_from_others(client, make_user):
    _, a = make_user("alice")
    _, b = make_user("bob")
    sid = client.post("/api/scenarios", json=_scenario_body("私密剧本"), headers=a).json()["id"]

    # B 看不到、读不到（私人 → 403）
    assert all(s["id"] != sid for s in client.get("/api/scenarios", headers=b).json()["scenarios"])
    assert client.get(f"/api/scenarios/{sid}", headers=b).status_code == 403

    # A 发布后，B 既能在列表看到、也能读到
    client.put(f"/api/scenarios/{sid}", json=_scenario_body("私密剧本", "published"), headers=a)
    assert any(s["id"] == sid for s in client.get("/api/scenarios", headers=b).json()["scenarios"])
    assert client.get(f"/api/scenarios/{sid}", headers=b).status_code == 200


def test_scenario_admin_sees_all_with_author(client, make_user, admin_headers):
    _, a = make_user("alice")
    sid = client.post("/api/scenarios", json=_scenario_body("alice私密"), headers=a).json()["id"]
    lst = client.get("/api/scenarios", headers=admin_headers).json()["scenarios"]
    row = next(s for s in lst if s["id"] == sid)
    assert row["author"] == "alice" and row["is_mine"] is False


def test_scenario_copy(client, make_user):
    """复制别人的已发布剧本 → 得到我的私人副本（内容一致、归属转移、可见性 private）。"""
    _, a = make_user("alice")
    _, b = make_user("bob")
    sid = client.post("/api/scenarios", json=_scenario_body("原作", "published"), headers=a).json()["id"]

    cp = client.post(f"/api/scenarios/{sid}/copy", headers=b)
    assert cp.status_code == 200
    new_id = cp.json()["id"]
    assert new_id != sid and cp.json()["visibility"] == "private" and "副本" in cp.json()["title"]

    # 副本归 B、内容与原作一致
    got = client.get(f"/api/scenarios/{new_id}", headers=b).json()
    assert got["author_id"] is not None
    assert "scar" in got["content"]["角色卡"]
    mine = next(s for s in client.get("/api/scenarios", headers=b).json()["scenarios"] if s["id"] == new_id)
    assert mine["is_mine"]


def test_scenario_copy_private_forbidden(client, make_user):
    """不能复制看不到的私人剧本（读授权边界）。"""
    _, a = make_user("alice")
    _, b = make_user("bob")
    sid = client.post("/api/scenarios", json=_scenario_body("私密"), headers=a).json()["id"]
    assert client.post(f"/api/scenarios/{sid}/copy", headers=b).status_code == 403


def test_scenario_non_owner_cannot_modify(client, make_user):
    _, a = make_user("alice")
    _, b = make_user("bob")
    sid = client.post("/api/scenarios", json=_scenario_body("alice的", "published"), headers=a).json()["id"]
    # B 即使能读（已发布），也不能改/删
    assert client.put(f"/api/scenarios/{sid}", json=_scenario_body("篡改"), headers=b).status_code == 403
    assert client.delete(f"/api/scenarios/{sid}", headers=b).status_code == 403


# ───────────────── 游戏：开局快照 + 拥有权 ─────────────────
def test_new_game_fog_and_panels(client, tavern_scenario):
    """开局快照：迷雾正确 + 结构化「角色」面板（我方详尽/敌方隐藏）+ 结构化「日志」。"""
    sid, headers = tavern_scenario
    r = client.post("/api/game/new", json={"scenario_id": sid}, headers=headers).json()
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
        assert client.get(f"/api/game/{gid}", headers=headers).json()["game_id"] == gid
        assert any(g["game_id"] == gid for g in client.get("/api/games", headers=headers).json()["games"])
    finally:
        client.delete(f"/api/game/{gid}", headers=headers)


def test_new_game_requires_auth(client, tavern_scenario):
    sid, _ = tavern_scenario
    assert client.post("/api/game/new", json={"scenario_id": sid}).status_code == 401


def test_new_game_unknown_scenario(client, user_headers):
    assert client.post("/api/game/new", json={"scenario_id": 999999},
                       headers=user_headers).status_code == 404


def test_new_game_private_scenario_forbidden(client, make_user):
    _, a = make_user("alice")
    _, b = make_user("bob")
    sid = client.post("/api/scenarios", json=_scenario_body("alice私密"), headers=a).json()["id"]
    # B 不能用 A 的私人剧本开局
    assert client.post("/api/game/new", json={"scenario_id": sid}, headers=b).status_code == 403


def test_game_ownership_hidden_from_others(client, tavern_scenario, make_user):
    """游戏永远私人：别人取/删别人的游戏 → 404（不泄露存在性）。"""
    sid, a = tavern_scenario
    _, b = make_user("bob")
    gid = client.post("/api/game/new", json={"scenario_id": sid}, headers=a).json()["game_id"]
    try:
        assert client.get(f"/api/game/{gid}", headers=b).status_code == 404
        assert client.delete(f"/api/game/{gid}", headers=b).status_code == 404
        # B 自己的游戏列表里看不到 A 的游戏
        assert all(g["game_id"] != gid for g in client.get("/api/games", headers=b).json()["games"])
    finally:
        client.delete(f"/api/game/{gid}", headers=a)


def test_game_admin_sees_owner(client, tavern_scenario, admin_headers):
    sid, a = tavern_scenario
    gid = client.post("/api/game/new", json={"scenario_id": sid}, headers=a).json()["game_id"]
    try:
        games = client.get("/api/games", headers=admin_headers).json()["games"]
        row = next(g for g in games if g["game_id"] == gid)
        assert row["owner"] == "author"      # tavern_scenario 的拥有者用户名
    finally:
        client.delete(f"/api/game/{gid}", headers=a)
