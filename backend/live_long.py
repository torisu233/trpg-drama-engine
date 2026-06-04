"""長跑 live 測試（會打 grok-3，較耗 API）：自動連打約 12 拍。
驗證 A 滾動摘要（跨 10 條門檻觸發）+ B 瞬態 TTL（裁決設剩餘拍數、自動過期）。

執行： python -m backend.live_long
"""
import asyncio
from .scene import new_tavern_session
from . import flow, engine
from .grok_client import GrokClient

ACTIONS = [
    {"行動": "按兵不動，冷眼打量刀疤的破綻", "目標": None, "隱蔽": False},
    {"行動": "沉聲說債好商量，今晚見血對誰都沒好處", "目標": "scar", "隱蔽": False},
    {"行動": "追問究竟是誰指使他來討這筆債", "目標": "scar", "隱蔽": False},
    {"行動": "不動聲色挪向牆角的油燈", "目標": None, "隱蔽": False},
    {"行動": "抄起油燈逼近，火光直照他的臉", "目標": "scar", "隱蔽": False},
    {"行動": "趁他退縮，短刃直取他持刀的手腕", "目標": "scar", "隱蔽": False},
]
REACTION = {"類型": "格擋", "方式": "側身抬臂擋開，順勢後撤半步"}


async def main():
    grok = GrokClient()
    s = new_tavern_session()
    await flow.advance(grok, s)
    ai = 0
    while not s.結束 and s.回合數 < 12:
        p = s.pending or {}
        if p.get("type") == "player_action":
            act = ACTIONS[ai % len(ACTIONS)]
            ai += 1
            print(f"  >> 玩家[{s.回合數}]：{act['行動']} {act.get('方式','')}")
            await flow.submit_player_action(grok, s, act)
        elif p.get("type") == "player_reaction":
            print(f"  >> 玩家反應[{s.回合數}]：{REACTION['類型']}（來襲：{p.get('incoming','')[:30]}…）")
            await flow.submit_player_reaction(grok, s, REACTION)
        else:
            await flow.advance(grok, s)

    print(f"\n===== 跑了 {s.回合數} 拍 =====")
    for cid in ("scar", "aqing"):
        print(f"\n[{cid}] 近期記憶 {len(s.記憶.get(cid, []))} 條")
        print(f"[{cid}] 滾動摘要：{s.摘要.get(cid) or '（尚未壓縮）'}")
    print("\n===== 帳本當前（看瞬態 TTL 有沒有清掉）=====")
    print(engine.ground_truth(s))
    await grok.close()


if __name__ == "__main__":
    asyncio.run(main())
