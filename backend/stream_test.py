"""验证串流：开一局，用串流送一个行动，确认逐拍收到 snapshot（会打 grok）。
运行： python -m backend.stream_test
"""
import sys
import json
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from fastapi.testclient import TestClient
from .main import app
from . import scenario as scen, game_store
from .scene import new_tavern_session

SID = "_tavern_stream"   # 临时种子剧本（测完即删）


def run():
    c = TestClient(app)
    scen.save_scenario(scen.scenario_from_session(new_tavern_session(), SID))
    gid = c.post("/api/game/new", json={"scenario_id": SID}).json()["game_id"]
    print("开局:", gid)
    n = 0
    with c.stream("POST", f"/api/game/{gid}/action",
                  json={"action": {"行动": "猛地掀翻桌子撞向刀疤", "目标": "scar", "隐蔽": False}}) as r:
        for line in r.iter_lines():
            if not line.strip():
                continue
            snap = json.loads(line)
            n += 1
            bars = "  ".join(f"{b['名']}:{b['行动值']}/{b['门槛']}" for b in snap["行动条"])
            print(f"  ◆ 逐拍 #{n}: 回合={snap['回合数']} 日志={len(snap['公开日志'])}行 pending={snap['pending'] and snap['pending']['type']}")
            print(f"      行动条 {bars}")
            print(f"      最新叙事: {snap['公开日志'][-1][:60]}")
    print(f"\n总共逐拍收到 {n} 个 snapshot（>1 即代表串流逐拍生效）")
    (scen.SCENARIOS_DIR / f"{SID}.json").unlink(missing_ok=True)
    game_store.delete_game(gid)


if __name__ == "__main__":
    run()
