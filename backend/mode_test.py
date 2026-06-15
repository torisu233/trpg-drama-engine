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
        世界观=World(基调="市井人情，茶楼酒肆间的消息买卖", 背景="乱世里，消息比刀子值钱。",
                    法则=["江湖消息有价，掌柜见人说人话、待价而沽"]),
        scene=Scene(id="teahouse", 地点="午后茶楼雅座，邻桌人声嘈杂",
                    钩子="钱掌柜慢条斯理斟茶：「客官想打听的事……可不便宜啊。」",
                    在场=["player", "boss"]),
        角色卡={
            "player": CharCard(名="玩家", 阵营="我方", 扮演="玩家", 性别="男",
                               身份背景="寻仇的浪客", 动机目标="从掌柜口中问出仇家下落",
                               能力=["会看人说谎", "沉得住气"], 弱点=["银钱不多"]),
            "boss": CharCard(名="钱掌柜", 阵营="中立", 扮演="agent", 性别="男",
                             身份背景="茶楼掌柜，五十岁精明老头",
                             说话风格="慢条斯理、笑里藏话、爱擡价",
                             动机目标="多赚一笔又别惹麻烦",
                             行为偏好=["待价而沽", "看人下菜碟", "怕事"],
                             能力=["消息灵通", "油滑会看人"], 弱点=["贪财", "怕官府"]),
        },
        会变层=Ledger(
            角色={
                "player": CharLedger(姿势位置="坐在掌柜对面", 行动速度=5),
                "boss": CharLedger(姿势位置="隔桌斟茶", 行动速度=5),
            },
            场景=SceneLedger(
                场景事实=[Condition(内容="茶楼人多嘈杂，谈话不易被外人听清", 可见性="public")],
                社会事实=[Condition(内容="玩家想打听仇家下落，掌柜开价未定",
                                  gates="谈妥价码才肯说", 可见性="public")]),
        ),
    )


async def main():
    grok = GrokClient()
    s = scen.session_from_scenario(build())
    await flow.advance(grok, s)
    print(">> pending:", s.pending and s.pending.get("type"))
    print(">> 玩家交涉：先付一半订金、事成再给，顺带暗示自己惹不起")
    async for _ in flow.stream_action(grok, s, {
        "行动": "压低声音说只要一个地址，先付一半订金、事成再给；顺带不着痕迹提一句自己惹不起",
        "目标": "boss", "隐蔽": False}):
        pass

    print("\n========== 公开日志 ==========")
    for line in s.公开日志:
        print(line)
    print("\n========== 账本（看后果是社会的还是被硬塞伤势）==========")
    print(engine.ground_truth(s))
    await grok.close()


if __name__ == "__main__":
    asyncio.run(main())
