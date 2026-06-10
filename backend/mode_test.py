"""驗證非戰鬥模式：手搭一個純交涉場景跑一拍（會打 grok-3）。
執行： python -m backend.mode_test
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
        id="茶樓",
        世界觀=World(基調="市井人情，茶樓酒肆間的消息買賣", 背景="亂世裡，消息比刀子值錢。",
                    法則=["江湖消息有價，掌櫃見人說人話、待價而沽"]),
        scene=Scene(id="teahouse", 地點="午後茶樓雅座，鄰桌人聲嘈雜",
                    鉤子="錢掌櫃慢條斯理斟茶：「客官想打聽的事……可不便宜啊。」",
                    在場=["player", "boss"]),
        角色卡={
            "player": CharCard(名="玩家", 陣營="我方", 扮演="玩家", 性別="男",
                               身分背景="尋仇的浪客", 動機目標="從掌櫃口中問出仇家下落",
                               能力=["會看人說謊", "沉得住氣"], 弱點=["銀錢不多"]),
            "boss": CharCard(名="錢掌櫃", 陣營="中立", 扮演="agent", 性別="男",
                             身分背景="茶樓掌櫃，五十歲精明老頭",
                             說話風格="慢條斯理、笑裡藏話、愛抬價",
                             動機目標="多賺一筆又別惹麻煩",
                             行為偏好=["待價而沽", "看人下菜碟", "怕事"],
                             能力=["消息靈通", "油滑會看人"], 弱點=["貪財", "怕官府"]),
        },
        會變層=Ledger(
            角色={
                "player": CharLedger(姿勢位置="坐在掌櫃對面", 行動速度=5),
                "boss": CharLedger(姿勢位置="隔桌斟茶", 行動速度=5),
            },
            場景=SceneLedger(
                場景事實=[Condition(內容="茶樓人多嘈雜，談話不易被外人聽清", 可見性="public")],
                社會事實=[Condition(內容="玩家想打聽仇家下落，掌櫃開價未定",
                                  gates="談妥價碼才肯說", 可見性="public")]),
        ),
    )


async def main():
    grok = GrokClient()
    s = scen.session_from_scenario(build())
    await flow.advance(grok, s)
    print(">> pending:", s.pending and s.pending.get("type"))
    print(">> 玩家交涉：先付一半訂金、事成再給，順帶暗示自己惹不起")
    await flow.submit_player_action(grok, s, {
        "行動": "壓低聲音說只要一個地址，先付一半訂金、事成再給；順帶不著痕跡提一句自己惹不起",
        "目標": "boss", "隱蔽": False})

    print("\n========== 公開日誌 ==========")
    for line in s.公開日誌:
        print(line)
    print("\n========== 帳本（看後果是社會的還是被硬塞傷勢）==========")
    print(engine.ground_truth(s))
    await grok.close()


if __name__ == "__main__":
    asyncio.run(main())
