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

    print("\n>> 玩家複合行動：佯攻刀疤 + 暗號示意阿青繞後（測試敘事歸屬是否正確）")
    await flow.submit_player_action(grok, s, {
        "行動": "佯攻刀疤、同時用左手對阿青使眼色要他繞到背後", "目標": "scar", "隱蔽": True,
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
