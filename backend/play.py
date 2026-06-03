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
        act = input("\n▶ 你的行動（攻擊/說服/後撤/對話/移動/按兵不動）> ").strip()
        if act in ("quit", "q"):
            return "quit"
        if handle_command(act, s):
            continue
        if not act:
            act = "按兵不動"
        tgt_raw = input("  目標（刀疤 / 阿青 / 留空=無對象）> ").strip().lower()
        if tgt_raw in ("quit", "q"):
            return "quit"
        if handle_command(tgt_raw, s):
            continue
        目標 = TARGET_ALIAS.get(tgt_raw, tgt_raw or None)
        方式 = input("  方式（具體怎麼做，一句話）> ").strip()
        隱蔽 = input("  隱蔽行動？(y/N) > ").strip().lower() in ("y", "yes")
        return {"行動": act, "目標": 目標, "方式": 方式, "隱蔽": 隱蔽}


def ask_reaction(s, incoming: str):
    """回傳 reaction dict，或字串指令 'quit'。"""
    print(f"\n{'⚔'*3} 來襲：{incoming}")
    print("    你必須反應！")
    while True:
        typ = input("▶ 反應類型（閃避/格擋/反擊/硬抗/後仰躲開…）> ").strip()
        if typ in ("quit", "q"):
            return "quit"
        if handle_command(typ, s):
            continue
        if not typ:
            typ = "硬抗"
        方式 = input("  方式（具體怎麼做）> ").strip()
        return {"類型": typ, "方式": 方式}


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
