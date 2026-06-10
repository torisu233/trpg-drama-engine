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
from . import scenario as scen, game_store
from .scene import new_tavern_session

SID = "_tavern_smoke"   # 臨時種子劇本（測完即刪），不依賴 scenarios/ 內容


def run():
    c = TestClient(app)
    # 用 in-code 酒館 fixture 落地一份臨時劇本，讓測試自給自足
    scen.save_scenario(scen.scenario_from_session(new_tavern_session(), SID))
    gid = None
    try:
        assert c.get("/api/health").json()["ok"] is True

        scs = c.get("/api/scenarios").json()["scenarios"]
        assert SID in scs, scs

        sc = c.get(f"/api/scenarios/{SID}").json()
        assert sc["id"] == SID and "scar" in sc["角色卡"]
        assert c.get("/api/scenarios/不存在").status_code == 404

        # 開新遊戲：酒館玩家速度高→先手→advance 立即停在 player_action，不打 grok
        r = c.post("/api/game/new", json={"scenario_id": SID}).json()
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
        print("  new game:", gid, "｜pending:", r["pending"]["type"], "｜公開日誌行數:", len(r["公開日誌"]))
        print("  存檔遊戲:", [g["game_id"] for g in games])
    finally:
        (scen.SCENARIOS_DIR / f"{SID}.json").unlink(missing_ok=True)   # 清掉臨時劇本
        if gid:
            game_store.delete_game(gid)                                 # 清掉臨時存檔


if __name__ == "__main__":
    run()
    print("\nAPI 煙霧測試通過 ✅")
