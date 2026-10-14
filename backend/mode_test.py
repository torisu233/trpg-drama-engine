"""验证非战斗模式：手搭一个纯交涉场景跑一拍（会打 LLM / DeepSeek）。
运行： python -m backend.mode_test
"""
import asyncio
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from .models import Scenario, World, Scene, CharCard, Ledger, CharLedger, SceneLedger, Condition
from . import scenario as scen, flow, engine
from .grok_client import GrokClient


def build() -> Scenario:
    return Scenario(
        id="茶楼",
        world=World(tone="市井人情，茶楼酒肆间的消息买卖", background="乱世里，消息比刀子值钱。",
                    laws=["江湖消息有价，掌柜见人说人话、待价而沽"]),
        scene=Scene(id="teahouse", location="午后茶楼雅座，邻桌人声嘈杂",
                    hook="钱掌柜慢条斯理斟茶：「客官想打听的事……可不便宜啊。」",
                    present=["player", "boss"]),
        cards={
            "player": CharCard(name="player", faction="ally", controller="player", gender="男",
                               backstory="寻仇的浪客", motive="从掌柜口中问出仇家下落",
                               abilities=["会看人说谎", "沉得住气"], weaknesses=["银钱不多"]),
            "boss": CharCard(name="钱掌柜", faction="neutral", controller="agent", gender="男",
                             backstory="茶楼掌柜，五十岁精明老头",
                             voice="慢条斯理、笑里藏话、爱擡价",
                             motive="多赚一笔又别惹麻烦",
                             tactics=["待价而沽", "看人下菜碟", "怕事"],
                             abilities=["消息灵通", "油滑会看人"], weaknesses=["贪财", "怕官府"]),
        },
        ledger=Ledger(
            characters={
                "player": CharLedger(posture="坐在掌柜对面", speed=5),
                "boss": CharLedger(posture="隔桌斟茶", speed=5),
            },
            scene=SceneLedger(
                scene_facts=[Condition(content="茶楼人多嘈杂，谈话不易被外人听清", visibility="public")],
                social_facts=[Condition(content="玩家想打听仇家下落，掌柜开价未定",
                                  gates="谈妥价码才肯说", visibility="public")]),
        ),
    )


async def main():
    grok = GrokClient()
    s = scen.session_from_scenario(build())
    await flow.advance(grok, s)
    print(">> pending:", s.pending and s.pending.get("type"))
    print(">> 玩家交涉：先付一半订金、事成再给，顺带暗示自己惹不起")
    async for _ in flow.stream_action(grok, s, {
        "action": "压低声音说只要一个地址，先付一半订金、事成再给；顺带不着痕迹提一句自己惹不起",
        "target": "boss", "covert": False}):
        pass

    print("\n========== public_log ==========")
    for line in s.public_log:
        print(line)
    print("\n========== 账本（看后果是社会的还是被硬塞伤势）==========")
    print(engine.ground_truth(s))
    await grok.close()


if __name__ == "__main__":
    asyncio.run(main())
