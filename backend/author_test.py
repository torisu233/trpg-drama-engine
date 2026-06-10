"""腳本化測試編劇 agent 核心（會打 grok-3）。

執行： python -m backend.author_test
"""
import asyncio
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from .models import Scenario
from . import scenario as scen, agents
from .grok_client import GrokClient

MSGS = [
    "武俠劇本：落魄鏢師在邊城客棧被陰險劍客堵上，有個莽撞講義氣的女隊友阿菊。先把世界觀和場景定了。",
    "建立玩家（主角鏢師）的角色卡。",
    "建立仇家劍客的角色卡，幫他埋一個秘密弱點。",
]


async def main():
    grok = GrokClient()
    sc = Scenario(id="邊城客棧_test")
    history = []
    for m in MSGS:
        print("\n" + "═" * 64)
        print("使用者：", m)
        history.append(("使用者", m))
        rep = await agents.author_turn(grok, sc, history, m)
        更新 = scen.apply_author_reply(sc, rep)
        history.append(("編劇", rep.reply))
        print("編劇：", rep.reply)
        print(f"→ 更新區塊：{更新}{('/'+rep.char_id) if rep.char_id else ''}｜missing={rep.missing}｜done={rep.done}")

    print("\n" + "═" * 64, "\n最終劇本摘要：")
    print(agents._scenario_brief(sc))
    print("\n角色卡 ids：", list(sc.角色卡.keys()), "｜在場：", sc.scene.在場)
    print("\n完整 JSON（前 2200 字）：")
    print(sc.model_dump_json(indent=2)[:2200])
    await grok.close()


if __name__ == "__main__":
    asyncio.run(main())
