"""命令行編劇工具：與編劇 agent 對話，逐區塊設計一份劇本，存成 scenarios/*.json。

執行： python -m backend.author

指令：
    /save [id]   存檔（可改 id）
    /show        印出當前劇本完整 JSON
    /list        列出已存劇本
    /load <id>   載入既有劇本繼續編
    /play        把當前劇本存檔後提示如何試玩
    /quit        離開
其餘輸入＝對編劇說的話（描述需求、要求調整）。
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

LINE = "─" * 60


def show_brief(sc: Scenario):
    print(f"\n{LINE}\n【當前劇本：{sc.id}】\n{agents._scenario_brief(sc)}\n{LINE}")


async def main():
    print("══ 編劇工具 ══  跟我說你想要的劇本（世界、場景、角色…），我邊問邊填。")
    print("指令：/save [id]  /show  /list  /load <id>  /play  /quit")
    grok = GrokClient()
    print("\n現有劇本：", scen.list_scenarios() or "（無）")
    名 = input("載入哪個繼續編？(Enter=新建) > ").strip()
    if 名 and 名 in scen.list_scenarios():
        sc = scen.load_scenario(名)
    else:
        sc = Scenario(id=名 or "新劇本")

    history = []
    try:
        while True:
            show_brief(sc)
            msg = input("\n你> ").strip()
            if not msg:
                continue
            if msg in ("/quit", "/q"):
                break
            if msg == "/list":
                print("現有劇本：", scen.list_scenarios() or "（無）")
                continue
            if msg == "/show":
                print(sc.model_dump_json(indent=2))
                continue
            if msg.startswith("/save") or msg == "/play":
                parts = msg.split()
                if len(parts) > 1:
                    sc.id = parts[1]
                p = scen.save_scenario(sc)
                print(f"已存：{p}")
                if msg == "/play":
                    print(f"試玩：改 play.py 載入 '{sc.id}'，或日後用選單載入。")
                continue
            if msg.startswith("/load"):
                parts = msg.split()
                if len(parts) > 1 and parts[1] in scen.list_scenarios():
                    sc = scen.load_scenario(parts[1])
                    history = []
                    print(f"已載入 {parts[1]}")
                else:
                    print("找不到該劇本。/list 看清單。")
                continue

            # 否則：對編劇說話
            history.append(("使用者", msg))
            print("\n…（編劇思考中）…")
            rep = await agents.author_turn(grok, sc, history, msg)
            更新 = scen.apply_author_reply(sc, rep)
            history.append(("編劇", rep.reply))
            print(f"\n編劇：{rep.reply}")
            if 更新 != "none":
                tag = 更新 + (f"/{rep.char_id}" if rep.char_id else "")
                print(f"（已更新區塊：{tag}）")
            if rep.missing:
                print(f"（待補：{'、'.join(rep.missing)}）")
            if rep.done:
                print("（✓ 劇本已足夠完整，可 /save）")
    finally:
        await grok.close()
        print("\n（離開編劇工具）")


if __name__ == "__main__":
    asyncio.run(main())
