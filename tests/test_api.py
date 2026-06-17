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


def test_change_password(client, make_user):
    """改密码：旧密码错→400；新密码太短→400；正确→200，且旧密码失效、新密码可登。"""
    _, h = make_user("carol", password="oldpass1")
    # 旧密码错
    assert client.post("/api/auth/change-password",
                       json={"old_password": "WRONG", "new_password": "newpass1"}, headers=h).status_code == 400
    # 新密码太短
    assert client.post("/api/auth/change-password",
                       json={"old_password": "oldpass1", "new_password": "123"}, headers=h).status_code == 400
    # 正确
    assert client.post("/api/auth/change-password",
                       json={"old_password": "oldpass1", "new_password": "newpass1"}, headers=h).status_code == 200
    # 旧密码登不上、新密码能登
    assert client.post("/api/auth/login", json={"username": "carol", "password": "oldpass1"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "carol", "password": "newpass1"}).status_code == 200


def test_change_password_requires_auth(client):
    assert client.post("/api/auth/change-password",
                       json={"old_password": "a", "new_password": "newpass1"}).status_code == 401


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
    assert "背景" in mine                       # 列表带背景摘要字段(供首页卡片显示)

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
        # 迷雾：上帝视角（账本调试）有敌方秘密；玩家侧不泄露由下方「角色」面板断言覆盖
        assert "怕火" in r["账本调试"]
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


@pytest.mark.parametrize("content, why", [
    ({"id": "无玩家", "scene": {"id": "s", "地点": "x", "在场": ["e1"]},
      "角色卡": {"e1": {"名": "匪", "阵营": "敌", "扮演": "agent"}}}, "无玩家"),
    ({"id": "玩家不在场", "scene": {"id": "s", "地点": "x", "在场": ["e1"]},
      "角色卡": {"p1": {"名": "侠", "阵营": "我方", "扮演": "玩家"},
                "e1": {"名": "匪", "阵营": "敌", "扮演": "agent"}}}, "玩家不在场"),
    ({"id": "空在场", "scene": {"id": "s", "地点": "x", "在场": []}, "角色卡": {}}, "空在场"),
], ids=["无玩家", "玩家不在场", "空在场"])
def test_new_game_incomplete_scenario_rejected(client, user_headers, content, why):
    """不完整剧本能保存，但开局被闸门挡成清晰 400（而非 500 或无限 LLM 循环挂起）。"""
    sid = client.post("/api/scenarios",
                      json={"scenario": content, "visibility": "private"},
                      headers=user_headers).json()["id"]
    r = client.post("/api/game/new", json={"scenario_id": sid}, headers=user_headers)
    assert r.status_code == 400 and "剧本不完整" in r.json()["detail"]


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
        assert row["剧本名"] == "_pytest_tavern"   # 游戏列表显示剧本名(而非地点)
    finally:
        client.delete(f"/api/game/{gid}", headers=a)


# ───────────────── AI 推荐玩家行为（只读端点）─────────────────
class _FakeGrok:
    """离线假 grok：character_intent/reaction 会调它，返回固定 Intent/Reaction。"""
    async def call(self, prompt, schema, **kw):
        if schema.__name__ == "Intent":
            return schema(行动="缓缓起身按住短刃，盯着刀疤", 目标="刀疤")   # 目标用名，端点应 resolve 成 id
        if schema.__name__ == "Reaction":
            return schema(反应="侧身避开，反手扣腕")
        return schema()
    async def close(self):
        pass


def test_suggest_action(client, tavern_scenario, monkeypatch):
    """玩家行动点：suggest 返回 action 建议；目标名被 resolve 成 id；只读不改局面。"""
    monkeypatch.setattr("backend.routes.game.get_grok", lambda: _FakeGrok())
    sid, headers = tavern_scenario
    gid = client.post("/api/game/new", json={"scenario_id": sid}, headers=headers).json()["game_id"]
    try:
        before = client.get(f"/api/game/{gid}", headers=headers).json()
        r = client.get(f"/api/game/{gid}/suggest", headers=headers)
        assert r.status_code == 200
        sug = r.json()["建议"]
        assert sug["类型"] == "action"
        assert "短刃" in sug["行动"]
        assert sug["目标id"] == "scar" and sug["目标名"] == "刀疤"   # 名→id
        # 只读：回合数/pending 不变
        after = client.get(f"/api/game/{gid}", headers=headers).json()
        assert after["回合数"] == before["回合数"] and after["pending"] == before["pending"]
    finally:
        client.delete(f"/api/game/{gid}", headers=headers)


def test_suggest_null_when_not_player_turn(client, tavern_scenario, db):
    """非玩家决策点(pending=None)→ 建议为 None，且无需调 grok（提前返回）。"""
    from backend import game_store
    sid, headers = tavern_scenario
    gid = client.post("/api/game/new", json={"scenario_id": sid}, headers=headers).json()["game_id"]
    try:
        row = game_store.load_game(db, gid)
        s = game_store.session_of(row)
        s.pending = None
        game_store.save_game(db, gid, s)
        r = client.get(f"/api/game/{gid}/suggest", headers=headers).json()
        assert r["建议"] is None
    finally:
        client.delete(f"/api/game/{gid}", headers=headers)


def test_suggest_requires_ownership(client, tavern_scenario, make_user):
    """别人的游戏 → 404（不泄露存在性）。"""
    sid, owner = tavern_scenario
    gid = client.post("/api/game/new", json={"scenario_id": sid}, headers=owner).json()["game_id"]
    _, other = make_user("mallory")
    try:
        assert client.get(f"/api/game/{gid}/suggest", headers=other).status_code == 404
    finally:
        client.delete(f"/api/game/{gid}", headers=owner)


# ───────────────── 反馈聊天 ─────────────────
def test_feedback_flow(client, make_user, admin_headers):
    """用户发反馈 → admin 在列表看到(未读) → 打开标已读 → 回复 → 用户看到回复。"""
    _, u = make_user("dave")
    assert client.post("/api/feedback", json={"body": "有个建议"}, headers=u).status_code == 200

    mine = client.get("/api/feedback", headers=u).json()["messages"]
    assert len(mine) == 1 and mine[0]["body"] == "有个建议" and mine[0]["sender_is_admin"] is False

    threads = client.get("/api/feedback/threads", headers=admin_headers).json()["threads"]
    assert len(threads) == 1 and threads[0]["username"] == "dave" and threads[0]["unread"] == 1
    uid = threads[0]["user_id"]

    t = client.get(f"/api/feedback/{uid}", headers=admin_headers).json()
    assert len(t["messages"]) == 1 and t["username"] == "dave"
    # 打开后未读清零
    assert client.get("/api/feedback/threads", headers=admin_headers).json()["threads"][0]["unread"] == 0

    assert client.post(f"/api/feedback/{uid}", json={"body": "收到，谢谢"}, headers=admin_headers).status_code == 200
    mine2 = client.get("/api/feedback", headers=u).json()["messages"]
    assert len(mine2) == 2 and mine2[1]["sender_is_admin"] is True and mine2[1]["body"] == "收到，谢谢"


def test_feedback_admin_endpoints_require_admin(client, make_user, user_headers):
    """普通用户打不开 admin 反馈端点（后端硬把关，不靠前端）。"""
    make_user("dave")
    assert client.get("/api/feedback/threads", headers=user_headers).status_code == 403
    assert client.get("/api/feedback/1", headers=user_headers).status_code == 403
    assert client.post("/api/feedback/1", json={"body": "x"}, headers=user_headers).status_code == 403


@pytest.mark.parametrize("method, path", [
    ("get", "/api/feedback"), ("post", "/api/feedback"),
], ids=["读自己", "发反馈"])
def test_feedback_requires_auth(client, method, path):
    fn = getattr(client, method)
    kw = {"json": {"body": "x"}} if method == "post" else {}
    assert fn(path, **kw).status_code == 401
