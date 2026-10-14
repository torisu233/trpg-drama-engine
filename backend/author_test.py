"""脚本化测试编剧 agent 内核（会打 LLM / DeepSeek）。

运行： python -m backend.author_test
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
    "武侠剧本：落魄镖师在边城客栈被阴险剑客堵上，有个莽撞讲义气的女队友阿菊。先把世界观和场景定了。",
    "创建玩家（主角镖师）的角色卡。",
    "创建仇家剑客的角色卡，帮他埋一个秘密弱点。",
]


async def main():
    grok = GrokClient()
    sc = Scenario(id="边城客栈_test")
    history = []
    for m in MSGS:
        print("\n" + "═" * 64)
        print("用户：", m)
        history.append(("用户", m))
        rep = await agents.author_turn(grok, sc, history, m)
        更新 = scen.apply_author_reply(sc, rep)
        history.append(("编剧", rep.reply))
        print("编剧：", rep.reply)
        print(f"→ 更新区块：{更新}{('/'+rep.char_id) if rep.char_id else ''}｜missing={rep.missing}｜done={rep.done}")

    print("\n" + "═" * 64, "\n最终剧本摘要：")
    print(agents._scenario_brief(sc))
    print("\n角色卡 ids：", list(sc.cards.keys()), "｜present：", sc.scene.present)
    print("\n完整 JSON（前 2200 字）：")
    print(sc.model_dump_json(indent=2)[:2200])
    await grok.close()


if __name__ == "__main__":
    asyncio.run(main())
