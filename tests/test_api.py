"""Integration tests: hit real endpoints through FastAPI's TestClient (in-process, no LLM calls).

Integration test = several components running together (routes + auth + engine + DB access). Fixtures are in conftest.py:
`client` (TestClient) / `db` (direct session, DB emptied before use) / `make_user`, `user_headers`,
`admin_headers` (create users and issue JWTs) / `tavern_scenario` (persists a published tavern scenario).

Endpoints are DB-backed with JWT auth, so the focus here is **authorization boundaries** (401 not logged in / 403 forbidden /
404 doesn't leak existence) and **visibility/ownership**, plus the fog/panel/log structure of the game-start snapshot.
In a new game the player is fastest and the game stops at the player's decision point immediately, so the LLM is never called.
"""
import json
import pytest

from backend import scenario as scen
from backend.scene import new_tavern_session


def _scenario_body(name="Test scenario", visibility="private"):
    """Build a valid ScenarioSave request body (uses the tavern data, so it passes Scenario validation)."""
    sc = scen.scenario_from_session(new_tavern_session(), name)
    return {"scenario": sc.model_dump(mode="json"), "visibility": visibility}


# ───────────────── health check (no auth) ─────────────────
def test_health(client):
    assert client.get("/api/health").json()["ok"] is True


# ───────────────── auth: register / login / me ─────────────────
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
    ("ab",                "pw123456", "username too short"),
    ("x" * 33,            "pw123456", "username too long"),
    ("goodname",          "12345",    "password too short"),
], ids=["short-name", "long-name", "short-password"])
def test_register_validation(client, db, username, password, why):
    assert client.post("/api/auth/register",
                       json={"username": username, "password": password}).status_code == 400


def test_register_duplicate(client, make_user):
    make_user("alice")        # already exists
    assert client.post("/api/auth/register",
                       json={"username": "alice", "password": "pw123456"}).status_code == 400


def test_login_wrong_password(client, make_user):
    make_user("alice", password="rightpass")
    assert client.post("/api/auth/login",
                       json={"username": "alice", "password": "wrongpass"}).status_code == 401


@pytest.mark.parametrize("headers, expected", [
    (None,                                401),   # no token → blocked
    ({"Authorization": "Bearer rubbish"}, 401),   # invalid token → blocked
], ids=["no-token", "bad-token"])
def test_me_requires_auth(client, headers, expected):
    assert client.get("/api/auth/me", headers=headers or {}).status_code == expected


def test_change_password(client, make_user):
    """Change password: wrong old password → 400; new password too short → 400; correct → 200, the old password stops working and the new one logs in."""
    _, h = make_user("carol", password="oldpass1")
    # wrong old password
    assert client.post("/api/auth/change-password",
                       json={"old_password": "WRONG", "new_password": "newpass1"}, headers=h).status_code == 400
    # new password too short
    assert client.post("/api/auth/change-password",
                       json={"old_password": "oldpass1", "new_password": "123"}, headers=h).status_code == 400
    # correct
    assert client.post("/api/auth/change-password",
                       json={"old_password": "oldpass1", "new_password": "newpass1"}, headers=h).status_code == 200
    # the old password can't log in, the new one can
    assert client.post("/api/auth/login", json={"username": "carol", "password": "oldpass1"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "carol", "password": "newpass1"}).status_code == 200


def test_change_password_requires_auth(client):
    assert client.post("/api/auth/change-password",
                       json={"old_password": "a", "new_password": "newpass1"}).status_code == 401


# ───────────────── scenarios: auth + CRUD + visibility + ownership ─────────────────
def test_scenarios_require_auth(client):
    assert client.get("/api/scenarios").status_code == 401


def test_scenario_crud(client, user_headers):
    # create
    cr = client.post("/api/scenarios", json=_scenario_body("My scenario"), headers=user_headers)
    assert cr.status_code == 200
    sid = cr.json()["id"]
    assert isinstance(sid, int)

    # list: appears in my own list, marked is_mine
    lst = client.get("/api/scenarios", headers=user_headers).json()["scenarios"]
    mine = next(s for s in lst if s["id"] == sid)
    assert mine["is_mine"] and mine["title"] == "My scenario"
    assert "background" in mine                       # the list includes a background excerpt field (for the home page cards)

    # read: content is returned
    got = client.get(f"/api/scenarios/{sid}", headers=user_headers).json()
    assert got["id"] == sid and "scar" in got["content"]["cards"]

    # update: title + visibility
    upd = client.put(f"/api/scenarios/{sid}",
                     json=_scenario_body("Renamed", visibility="published"), headers=user_headers)
    assert upd.status_code == 200 and upd.json()["visibility"] == "published"
    assert client.get(f"/api/scenarios/{sid}", headers=user_headers).json()["title"] == "Renamed"

    # delete (soft): gone from the list, reading again → 404
    assert client.delete(f"/api/scenarios/{sid}", headers=user_headers).status_code == 200
    assert all(s["id"] != sid for s in client.get("/api/scenarios", headers=user_headers).json()["scenarios"])
    assert client.get(f"/api/scenarios/{sid}", headers=user_headers).status_code == 404


def test_scenario_visibility_private_hidden_from_others(client, make_user):
    _, a = make_user("alice")
    _, b = make_user("bob")
    sid = client.post("/api/scenarios", json=_scenario_body("Private scenario"), headers=a).json()["id"]

    # B can neither see nor read it (private → 403)
    assert all(s["id"] != sid for s in client.get("/api/scenarios", headers=b).json()["scenarios"])
    assert client.get(f"/api/scenarios/{sid}", headers=b).status_code == 403

    # after A publishes, B can both see it in the list and read it
    client.put(f"/api/scenarios/{sid}", json=_scenario_body("Private scenario", "published"), headers=a)
    assert any(s["id"] == sid for s in client.get("/api/scenarios", headers=b).json()["scenarios"])
    assert client.get(f"/api/scenarios/{sid}", headers=b).status_code == 200


def test_scenario_admin_sees_all_with_author(client, make_user, admin_headers):
    _, a = make_user("alice")
    sid = client.post("/api/scenarios", json=_scenario_body("alice private"), headers=a).json()["id"]
    lst = client.get("/api/scenarios", headers=admin_headers).json()["scenarios"]
    row = next(s for s in lst if s["id"] == sid)
    assert row["author"] == "alice" and row["is_mine"] is False


def test_scenario_copy(client, make_user):
    """Copying someone else's published scenario → my private copy (same content, ownership transferred, visibility private)."""
    _, a = make_user("alice")
    _, b = make_user("bob")
    sid = client.post("/api/scenarios", json=_scenario_body("Original", "published"), headers=a).json()["id"]

    cp = client.post(f"/api/scenarios/{sid}/copy", headers=b)
    assert cp.status_code == 200
    new_id = cp.json()["id"]
    assert new_id != sid and cp.json()["visibility"] == "private" and "(copy)" in cp.json()["title"]

    # the copy belongs to B, with the same content as the original
    got = client.get(f"/api/scenarios/{new_id}", headers=b).json()
    assert got["author_id"] is not None
    assert "scar" in got["content"]["cards"]
    mine = next(s for s in client.get("/api/scenarios", headers=b).json()["scenarios"] if s["id"] == new_id)
    assert mine["is_mine"]


def test_scenario_copy_private_forbidden(client, make_user):
    """You can't copy a private scenario you can't see (read authorization boundary)."""
    _, a = make_user("alice")
    _, b = make_user("bob")
    sid = client.post("/api/scenarios", json=_scenario_body("private"), headers=a).json()["id"]
    assert client.post(f"/api/scenarios/{sid}/copy", headers=b).status_code == 403


def test_scenario_non_owner_cannot_modify(client, make_user):
    _, a = make_user("alice")
    _, b = make_user("bob")
    sid = client.post("/api/scenarios", json=_scenario_body("alice's", "published"), headers=a).json()["id"]
    # even though B can read it (published), B can't update/delete it
    assert client.put(f"/api/scenarios/{sid}", json=_scenario_body("Tampered"), headers=b).status_code == 403
    assert client.delete(f"/api/scenarios/{sid}", headers=b).status_code == 403


# ───────────────── games: game-start snapshot + ownership ─────────────────
def test_new_game_fog_and_panels(client, tavern_scenario):
    """Game-start snapshot: correct fog + structured "characters" panel (allies detailed / enemies hidden) + structured "log"."""
    sid, headers = tavern_scenario
    r = client.post("/api/game/new", json={"scenario_id": sid}, headers=headers).json()
    gid = r["game_id"]
    try:
        assert r["pending"]["type"] == "player_action"
        assert any(l.startswith("[Opening] ") for l in r["public_log"])
        # fog: the god view (ledger_debug) has the enemy secret; the player side not leaking it is covered by the "characters" panel assertions below
        assert "afraid of fire" in r["ledger_debug"]
        # structured character panel: teammate cards visible, enemy cards not injected
        roles = {x["id"]: x for x in r["characters"]}
        assert roles["aqing"]["is_ally"] and roles["aqing"].get("abilities")
        assert "weaknesses" not in roles["scar"] and "abilities" not in roles["scar"]
        assert "afraid of fire" not in json.dumps(roles["scar"], ensure_ascii=False)
        # structured per-beat log: the opening is a system line (no actor)
        assert r["log"] and r["log"][0]["actor"] is None
        # fetch the snapshot, list in-progress games
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
    sid = client.post("/api/scenarios", json=_scenario_body("alice private"), headers=a).json()["id"]
    # B can't start a game with A's private scenario
    assert client.post("/api/game/new", json={"scenario_id": sid}, headers=b).status_code == 403


@pytest.mark.parametrize("content, why", [
    ({"id": "no-player", "scene": {"id": "s", "location": "x", "present": ["e1"]},
      "cards": {"e1": {"name": "Bandit", "faction": "enemy", "controller": "agent"}}}, "no player"),
    ({"id": "player-absent", "scene": {"id": "s", "location": "x", "present": ["e1"]},
      "cards": {"p1": {"name": "Hero", "faction": "ally", "controller": "player"},
                "e1": {"name": "Bandit", "faction": "enemy", "controller": "agent"}}}, "player not present"),
    ({"id": "nobody-present", "scene": {"id": "s", "location": "x", "present": []}, "cards": {}}, "nobody present"),
], ids=["no-player", "player-absent", "nobody-present"])
def test_new_game_incomplete_scenario_rejected(client, user_headers, content, why):
    """An incomplete scenario can be saved, but the game-start gate rejects it with a clear 400 (instead of a 500 or hanging in an infinite LLM loop)."""
    sid = client.post("/api/scenarios",
                      json={"scenario": content, "visibility": "private"},
                      headers=user_headers).json()["id"]
    r = client.post("/api/game/new", json={"scenario_id": sid}, headers=user_headers)
    assert r.status_code == 400 and "Scenario is incomplete" in r.json()["detail"]


def test_game_ownership_hidden_from_others(client, tavern_scenario, make_user):
    """Games are always private: fetching/deleting someone else's game → 404 (doesn't leak existence)."""
    sid, a = tavern_scenario
    _, b = make_user("bob")
    gid = client.post("/api/game/new", json={"scenario_id": sid}, headers=a).json()["game_id"]
    try:
        assert client.get(f"/api/game/{gid}", headers=b).status_code == 404
        assert client.delete(f"/api/game/{gid}", headers=b).status_code == 404
        # A's game doesn't appear in B's own game list
        assert all(g["game_id"] != gid for g in client.get("/api/games", headers=b).json()["games"])
    finally:
        client.delete(f"/api/game/{gid}", headers=a)


def test_game_admin_sees_owner(client, tavern_scenario, admin_headers):
    sid, a = tavern_scenario
    gid = client.post("/api/game/new", json={"scenario_id": sid}, headers=a).json()["game_id"]
    try:
        games = client.get("/api/games", headers=admin_headers).json()["games"]
        row = next(g for g in games if g["game_id"] == gid)
        assert row["owner"] == "author"      # owner username of tavern_scenario
        assert row["scenario_name"] == "_pytest_tavern"   # the game list shows the scenario name (not the location)
    finally:
        client.delete(f"/api/game/{gid}", headers=a)


# ───────────────── AI-suggested player move (read-only endpoint) ─────────────────
class _FakeLLM:
    """Offline fake LLM: character_intent/reaction call it; returns a fixed Intent/Reaction."""
    async def call(self, prompt, schema, **kw):
        if schema.__name__ == "Intent":
            return schema(action="Slowly rises, hand on the short blade, eyes fixed on Scar", target="Scar")   # target by name; the endpoint should resolve it to an id
        if schema.__name__ == "Reaction":
            return schema(reaction="Sidesteps and grabs the wrist with a backhand")
        return schema()
    async def close(self):
        pass


def test_suggest_action(client, tavern_scenario, monkeypatch):
    """At the player action point: suggest returns an action suggestion; the target name is resolved to an id; read-only, the situation is unchanged."""
    monkeypatch.setattr("backend.routes.game.get_llm", lambda: _FakeLLM())
    sid, headers = tavern_scenario
    gid = client.post("/api/game/new", json={"scenario_id": sid}, headers=headers).json()["game_id"]
    try:
        before = client.get(f"/api/game/{gid}", headers=headers).json()
        r = client.get(f"/api/game/{gid}/suggest", headers=headers)
        assert r.status_code == 200
        sug = r.json()["suggestion"]
        assert sug["kind"] == "action"
        assert "short blade" in sug["action"]
        assert sug["target_id"] == "scar" and sug["target_name"] == "Scar"   # name→id
        # read-only: turn/pending unchanged
        after = client.get(f"/api/game/{gid}", headers=headers).json()
        assert after["turn"] == before["turn"] and after["pending"] == before["pending"]
    finally:
        client.delete(f"/api/game/{gid}", headers=headers)


def test_suggest_null_when_not_player_turn(client, tavern_scenario, db):
    """Not at a player decision point (pending=None) → suggestion is None, and the LLM is never needed (early return)."""
    from backend import game_store
    sid, headers = tavern_scenario
    gid = client.post("/api/game/new", json={"scenario_id": sid}, headers=headers).json()["game_id"]
    try:
        row = game_store.load_game(db, gid)
        s = game_store.session_of(row)
        s.pending = None
        game_store.save_game(db, gid, s)
        r = client.get(f"/api/game/{gid}/suggest", headers=headers).json()
        assert r["suggestion"] is None
    finally:
        client.delete(f"/api/game/{gid}", headers=headers)


def test_suggest_requires_ownership(client, tavern_scenario, make_user):
    """Someone else's game → 404 (doesn't leak existence)."""
    sid, owner = tavern_scenario
    gid = client.post("/api/game/new", json={"scenario_id": sid}, headers=owner).json()["game_id"]
    _, other = make_user("mallory")
    try:
        assert client.get(f"/api/game/{gid}/suggest", headers=other).status_code == 404
    finally:
        client.delete(f"/api/game/{gid}", headers=owner)


# ───────────────── feedback chat ─────────────────
def test_feedback_flow(client, make_user, admin_headers):
    """User sends feedback → admin sees it in the list (unread) → opening marks it read → admin replies → user sees the reply."""
    _, u = make_user("dave")
    assert client.post("/api/feedback", json={"body": "I have a suggestion"}, headers=u).status_code == 200

    mine = client.get("/api/feedback", headers=u).json()["messages"]
    assert len(mine) == 1 and mine[0]["body"] == "I have a suggestion" and mine[0]["sender_is_admin"] is False

    threads = client.get("/api/feedback/threads", headers=admin_headers).json()["threads"]
    assert len(threads) == 1 and threads[0]["username"] == "dave" and threads[0]["unread"] == 1
    uid = threads[0]["user_id"]

    t = client.get(f"/api/feedback/{uid}", headers=admin_headers).json()
    assert len(t["messages"]) == 1 and t["username"] == "dave"
    # opening clears the unread count
    assert client.get("/api/feedback/threads", headers=admin_headers).json()["threads"][0]["unread"] == 0

    assert client.post(f"/api/feedback/{uid}", json={"body": "Got it, thanks"}, headers=admin_headers).status_code == 200
    mine2 = client.get("/api/feedback", headers=u).json()["messages"]
    assert len(mine2) == 2 and mine2[1]["sender_is_admin"] is True and mine2[1]["body"] == "Got it, thanks"


def test_feedback_admin_endpoints_require_admin(client, make_user, user_headers):
    """Regular users can't open admin feedback endpoints (enforced on the backend, not the frontend)."""
    make_user("dave")
    assert client.get("/api/feedback/threads", headers=user_headers).status_code == 403
    assert client.get("/api/feedback/1", headers=user_headers).status_code == 403
    assert client.post("/api/feedback/1", json={"body": "x"}, headers=user_headers).status_code == 403


@pytest.mark.parametrize("method, path", [
    ("get", "/api/feedback"), ("post", "/api/feedback"),
], ids=["read-own", "send-feedback"])
def test_feedback_requires_auth(client, method, path):
    fn = getattr(client, method)
    kw = {"json": {"body": "x"}} if method == "post" else {}
    assert fn(path, **kw).status_code == 401
