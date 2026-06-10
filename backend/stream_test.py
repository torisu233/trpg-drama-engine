"""驗證串流：開一局，用串流送一個行動，確認逐拍收到 snapshot（會打 grok）。
執行： python -m backend.stream_test
"""
import sys
import json
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from fastapi.testclient import TestClient
from .main import app


def run():
    c = TestClient(app)
    gid = c.post("/api/game/new", json={"scenario_id": "tavern"}).json()["game_id"]
    print("開局:", gid)
    n = 0
    with c.stream("POST", f"/api/game/{gid}/action",
                  json={"action": {"行動": "猛地掀翻桌子撞向刀疤", "目標": "scar", "隱蔽": False}}) as r:
        for line in r.iter_lines():
            if not line.strip():
                continue
            snap = json.loads(line)
            n += 1
            bars = "  ".join(f"{b['名']}:{b['行動值']}/{b['門檻']}" for b in snap["行動條"])
            print(f"  ◆ 逐拍 #{n}: 回合={snap['回合數']} 日誌={len(snap['公開日誌'])}行 pending={snap['pending'] and snap['pending']['type']}")
            print(f"      行動條 {bars}")
            print(f"      最新敘事: {snap['公開日誌'][-1][:60]}")
    print(f"\n總共逐拍收到 {n} 個 snapshot（>1 即代表串流逐拍生效）")


if __name__ == "__main__":
    run()
