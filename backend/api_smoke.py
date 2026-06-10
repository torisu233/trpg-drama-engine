"""API 煙霧測試（離線，用 TestClient；不打 grok）。

驗證非 LLM 的端點：health / scenarios CRUD / game.new（玩家先手，無 LLM）/ game.get / games。
執行： python -m backend.api_smoke
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from fastapi.testclient import TestClient
from .main import app


def run():
    c = TestClient(app)

    assert c.get("/api/health").json()["ok"] is True

    scs = c.get("/api/scenarios").json()["scenarios"]
    assert "tavern" in scs, scs

    sc = c.get("/api/scenarios/tavern").json()
    assert sc["id"] == "tavern" and "scar" in sc["角色卡"]
    assert c.get("/api/scenarios/不存在").status_code == 404

    # 開新遊戲：酒館玩家速度高→先手→advance 立即停在 player_action，不打 grok
    r = c.post("/api/game/new", json={"scenario_id": "tavern"}).json()
    gid = r["game_id"]
    assert r["pending"]["type"] == "player_action", r["pending"]
    assert any("開場" in line for line in r["公開日誌"])
    assert "怕火" not in r["玩家視圖"] and "怕火" in r["帳本除錯"]   # 迷霧仍正確

    snap = c.get(f"/api/game/{gid}").json()
    assert snap["game_id"] == gid

    games = c.get("/api/games").json()["games"]
    assert any(g["game_id"] == gid for g in games)

    assert c.post("/api/game/new", json={"scenario_id": "無此劇本"}).status_code == 404

    print("[API] health / scenarios(list,get,404) / game.new / game.get / games  全部 ✓")
    print("  scenarios:", scs)
    print("  new game:", gid, "｜pending:", r["pending"]["type"], "｜公開日誌行數:", len(r["公開日誌"]))
    print("  存檔遊戲:", [g["game_id"] for g in games])


if __name__ == "__main__":
    run()
    print("\nAPI 煙霧測試通過 ✅")
