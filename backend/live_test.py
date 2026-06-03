"""端到端 live 測試（會呼叫 grok-3，消耗 API）。
驗證階段 3-5：裁決 / 敘事 / 角色 agent / 迷霧分發 的真實迴圈。

執行： python -m backend.live_test
"""
import asyncio
from .scene import new_tavern_session
from . import flow, engine
from .grok_client import GrokClient


async def main():
    grok = GrokClient()
    s = new_tavern_session()

    await flow.advance(grok, s)
    print(f">> 開場 pending = {s.pending and s.pending.get('type')}（玩家速度高，應先手）")

    print("\n>> 玩家行動：亮刃說服刀疤")
    await flow.submit_player_action(grok, s, {
        "行動": "說服", "目標": "scar",
        "方式": "不動聲色亮出袖中短刃，冷聲說錢三日後雙倍奉還，今晚見血對誰都沒好處",
        "隱蔽": False,
    })

    print("\n========== 公開日誌 ==========")
    for line in s.公開日誌:
        print(line)

    print(f"\n========== 狀態 ==========")
    print(f"回合數={s.回合數}  結束={s.結束}")
    print(f"pending={s.pending}")

    print("\n========== 刀疤(scar) 的私密記憶 ==========")
    for m in s.記憶.get("scar", []):
        print(" -", m)

    print("\n========== 帳本當前(地面真相) ==========")
    print(engine.ground_truth(s))

    await grok.close()


if __name__ == "__main__":
    asyncio.run(main())
