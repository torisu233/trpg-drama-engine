"""命令行互動版（直接用後端引擎，免伺服器/瀏覽器）。

執行：
    cd trpg-drama-engine
    .\\.venv\\Scripts\\python.exe -m backend.play

指令（任何輸入提示下都可用）：
    view    查看你目前感知到的局面
    ledger  查看完整帳本（含 gm 秘密，開發用）
    quit    離開
"""
import asyncio
import sys

# 自行處理 Windows 主控台輸出編碼，免設 PYTHONIOENCODING
# （只調 stdout；stdin 在互動主控台由 OS 處理 Unicode，調了反而會吃掉管道首行）
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from .scene import new_tavern_session
from . import flow, engine
from .grok_client import GrokClient

LINE = "─" * 60
TARGET_ALIAS = {
    "scar": "scar", "刀疤": "scar", "敵": "scar", "1": "scar",
    "aqing": "aqing", "阿青": "aqing", "隊友": "aqing", "2": "aqing",
    "": None, "無": None, "none": None,
}


def show_new_log(s, shown: int) -> int:
    for line in s.公開日誌[shown:]:
        print("\n" + line)
    return len(s.公開日誌)


def handle_command(cmd: str, s) -> bool:
    """處理 view/ledger，回傳 True 表示已處理（呼叫端應 continue）。"""
    if cmd == "view":
        print(f"\n{LINE}\n【你感知到的局面】\n{engine.build_view(s, 'player')}\n{LINE}")
        return True
    if cmd == "ledger":
        print(f"\n{LINE}\n【完整帳本｜含 gm 秘密】\n{engine.ground_truth(s)}\n{LINE}")
        return True
    return False


def ask_action(s):
    """回傳 action dict，或字串指令 'quit'。"""
    while True:
        act = input("\n▶ 你想做什麼（一句話含做法；可附帶小動作，如攻擊同時對阿青使眼色）> ").strip()
        if act in ("quit", "q"):
            return "quit"
        if handle_command(act, s):
            continue
        if not act:
            act = "按兵不動"
        tgt_raw = input("  主要對象（刀疤 / 阿青 / 留空=無）> ").strip().lower()
        if tgt_raw in ("quit", "q"):
            return "quit"
        if handle_command(tgt_raw, s):
            continue
        目標 = TARGET_ALIAS.get(tgt_raw, tgt_raw or None)
        隱蔽 = input("  隱蔽？想瞞過敵人(潛行/暗號/偷偷拔刀)才選 y (y/N) > ").strip().lower() in ("y", "yes")
        return {"行動": act, "目標": 目標, "隱蔽": 隱蔽}


def ask_reaction(s, incoming: str):
    """回傳 reaction dict，或字串指令 'quit'。"""
    print(f"\n{'⚔'*3} 刀疤對你出招/喊話：{incoming}")
    print("    輪到你回應！")
    while True:
        r = input("▶ 你要如何回應（閃避/格擋/反擊/還嘴/喝止…，一句話含做法）> ").strip()
        if r in ("quit", "q"):
            return "quit"
        if handle_command(r, s):
            continue
        if not r:
            r = "硬抗"
        return {"反應": r}


async def main():
    print(LINE)
    print("  跑團原型 · 雨夜酒館   （你＝玩家，阿青＝隊友，刀疤＝敵）")
    print("  隨時可輸入  view / ledger / quit")
    print(LINE)

    grok = GrokClient()
    s = new_tavern_session()
    shown = 0
    try:
        await flow.advance(grok, s)
        shown = show_new_log(s, shown)

        while not s.結束:
            p = s.pending or {}
            if p.get("type") == "player_action":
                a = ask_action(s)
                if a == "quit":
                    print("\n（離開遊戲）")
                    break
                print("\n…（裁決與敘事中，請稍候）…")
                await flow.submit_player_action(grok, s, a)
                shown = show_new_log(s, shown)

            elif p.get("type") == "player_reaction":
                r = ask_reaction(s, p.get("incoming", ""))
                if r == "quit":
                    print("\n（離開遊戲）")
                    break
                print("\n…（裁決與敘事中，請稍候）…")
                await flow.submit_player_reaction(grok, s, r)
                shown = show_new_log(s, shown)
            else:
                # 沒有 pending 也沒結束（理論上不會發生），推一把
                await flow.advance(grok, s)
                shown = show_new_log(s, shown)

        if s.結束:
            print(f"\n{LINE}\n【場景結束】{s.結束}\n{LINE}")
    finally:
        await grok.close()


if __name__ == "__main__":
    asyncio.run(main())
