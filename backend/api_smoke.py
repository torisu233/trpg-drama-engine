"""API 烟雾测试（脱机，用 TestClient；不打 grok）。

验证非 LLM 的端点：health / scenarios CRUD / game.new（玩家先手，无 LLM）/ game.get / games。
运行： python -m backend.api_smoke
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

SID = "_tavern_smoke"   # 临时种子剧本（测完即删），不依赖 scenarios/ 内容


def run():
    c = TestClient(app)
    # 用 in-code 酒馆 fixture 落地一份临时剧本，让测试自给自足
    scen.save_scenario(scen.scenario_from_session(new_tavern_session(), SID))
    gid = None
    try:
        assert c.get("/api/health").json()["ok"] is True

        scs = c.get("/api/scenarios").json()["scenarios"]
        assert SID in scs, scs

        sc = c.get(f"/api/scenarios/{SID}").json()
        assert sc["id"] == SID and "scar" in sc["角色卡"]
        assert c.get("/api/scenarios/不存在").status_code == 404

        # 开新游戏：酒馆玩家速度高→先手→advance 立即停在 player_action，不打 grok
        r = c.post("/api/game/new", json={"scenario_id": SID}).json()
        gid = r["game_id"]
        assert r["pending"]["type"] == "player_action", r["pending"]
        assert any("开场" in line for line in r["公开日志"])
        assert "怕火" not in r["玩家视图"] and "怕火" in r["帐本调试"]   # 迷雾仍正确

        # 结构化局面 + 角色：我方给完整卡（能力/弱点）、敌方只给可见状态
        assert r["局面"]["场景"], r["局面"]
        roles = {x["id"]: x for x in r["角色"]}
        assert roles["aqing"]["是我方"] and roles["aqing"].get("能力")       # 队友：能力可见
        assert "scar" in roles and not roles["scar"]["是我方"]
        assert "弱点" not in roles["scar"] and "能力" not in roles["scar"]    # 敌方：卡不注入
        import json as _json
        assert "怕火" not in _json.dumps(roles["scar"], ensure_ascii=False)   # 敌方秘密不外泄

        snap = c.get(f"/api/game/{gid}").json()
        assert snap["game_id"] == gid

        games = c.get("/api/games").json()["games"]
        assert any(g["game_id"] == gid for g in games)

        assert c.post("/api/game/new", json={"scenario_id": "无此剧本"}).status_code == 404

        print("[API] health / scenarios(list,get,404) / game.new / game.get / games  全部 ✓")
        print("  new game:", gid, "｜pending:", r["pending"]["type"], "｜公开日志行数:", len(r["公开日志"]))
        print("  存盘游戏:", [g["game_id"] for g in games])
    finally:
        (scen.SCENARIOS_DIR / f"{SID}.json").unlink(missing_ok=True)   # 清掉临时剧本
        if gid:
            game_store.delete_game(gid)                                 # 清掉临时存盘


if __name__ == "__main__":
    run()
    print("\nAPI 烟雾测试通过 ✅")
