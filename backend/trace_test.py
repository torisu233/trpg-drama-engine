"""追蹤模式測試：腳本化玩家輸入，詳細展示每個環節的內部資料。

用包裝器掛在真實 pipeline（engine/agents）上，逐拍印出：
  行動條數值 / 兩軸判定 / 運氣 / 裁決完整輸出 / 敘事公開+私密 / TTL 清理 / 滾動摘要 / 迷霧視圖

執行： python -m backend.trace_test
（會打 grok-3，約 10 拍，耗數分鐘 API）
"""
import asyncio
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from .scene import new_tavern_session
from . import flow, engine, agents, config
from .grok_client import GrokClient

SEP = "═" * 72
SUB = "─" * 72


def banner(t):
    print(f"\n{SEP}\n{t}\n{SEP}")


def _count_conds(s):
    n = 0
    for cl in s.會變層.角色.values():
        n += len(cl.身心狀況) + len(cl.特殊情況)
    sc = s.會變層.場景
    return n + len(sc.場景事實) + len(sc.空間關係) + len(sc.社會事實)


# ───────── 包裝 engine（純邏輯環節）─────────
_pick = engine.pick_actor
def pick_actor(s):
    actor = _pick(s)
    bars = {c: cl.行動值 for c, cl in s.會變層.角色.items()}
    spd = {c: cl.行動速度 for c, cl in s.會變層.角色.items()}
    print(f"\n[行動條] 速度={spd}  累積後行動值={bars}  → 行動者：{actor}（門檻 {config.ACTION_THRESHOLD}）")
    return actor
engine.pick_actor = pick_actor

_nr = engine.needs_reaction
def needs_reaction(s, intent):
    r = _nr(s, intent)
    print(f"[軸A·反應] 目標={intent.目標} → " + (f"向「{r}」收反應" if r else "不收反應"))
    return r
engine.needs_reaction = needs_reaction

_ic = engine.is_contested
def is_contested(s, intent, rt):
    r = _ic(s, intent, rt)
    print(f"[軸B·爭議] → {'爭議（擲運氣）' if r else '非爭議（不擲）'}")
    return r
engine.is_contested = is_contested

_luck = engine.roll_luck
def roll_luck():
    r = _luck()
    print(f"[運氣神諭] 擲出：{r}（隱藏，僅裁決可見）")
    return r
engine.roll_luck = roll_luck

_apply = engine.apply_delta
def apply_delta(s, adj):
    _apply(s, adj)
engine.apply_delta = apply_delta

_expire = engine.expire_transients
def expire_transients(s):
    before = _count_conds(s)
    _expire(s)
    after = _count_conds(s)
    if before != after:
        print(f"[TTL·清理] 狀態條目 {before} → {after}（過期移除 {before - after} 條）")
engine.expire_transients = expire_transients


# ───────── 包裝 agents（LLM 環節）─────────
_ci = agents.character_intent
async def character_intent(grok, s, cid):
    print(f"\n{SUB}\n[角色意圖] 詢問 {cid}（{s.角色卡[cid].名}）")
    out = await _ci(grok, s, cid)
    print(f"  → 行動={out.行動!r}  目標={out.目標}  隱蔽={out.隱蔽}")
    return out
agents.character_intent = character_intent

_cr = agents.character_reaction
async def character_reaction(grok, s, cid, incoming):
    print(f"[角色反應] 詢問 {cid}（{s.角色卡[cid].名}）對來襲：{incoming[:46]}…")
    out = await _cr(grok, s, cid, incoming)
    print(f"  → 反應={out.反應!r}")
    return out
agents.character_reaction = character_reaction

_adj = agents.adjudicate
async def adjudicate(grok, s, intent, reaction, luck):
    rtxt = repr(reaction.反應) if reaction else None
    print(f"\n[裁決·輸入] 行動者={intent.actor} 行動={intent.行動!r} 反應={rtxt} 運氣={luck}")
    out = await _adj(grok, s, intent, reaction, luck)
    print("[裁決·輸出]")
    print(f"   相關狀態 : {out.相關狀態}")
    print(f"   逐條判定 : {out.逐條判定}")
    print(f"   可行性={out.可行性}  結果階梯={out.結果階梯}")
    for d in out.ledger_delta.add:
        print(f"   + [{d.主體}/{d.類別}] {d.內容}  ｜gates:{d.gates}｜{d.可見性}｜剩餘拍數:{d.剩餘拍數}")
    if out.ledger_delta.remove:
        print(f"   - remove: {out.ledger_delta.remove}")
    if out.速度更新:
        print(f"   速度更新: {out.速度更新}")
    if out.感知更新:
        print(f"   感知更新: {out.感知更新}")
    print(f"   感知分發 : {out.感知分發}")
    print(f"   GM摘要   : {out.GM摘要}")
    return out
agents.adjudicate = adjudicate

_nar = agents.narrate
async def narrate(grok, s, adj, intent, reaction=None):
    out = await _nar(grok, s, adj, intent, reaction)
    print(f"\n[敘事·公開] {out.公開}")
    for cid, txt in out.私密.items():
        print(f"[敘事·私密→{cid}] {txt}")
    return out
agents.narrate = narrate

_sum = agents.summarize_memory
async def summarize_memory(grok, s, cid, old, evicted):
    print(f"\n[滾動摘要] {cid} 觸發（記憶達 {2*config.KEEP_RECENT}）：摺入最舊 {len(evicted)} 條")
    out = await _sum(grok, s, cid, old, evicted)
    print(f"   新摘要：{out}")
    return out
agents.summarize_memory = summarize_memory


# ───────── 腳本化玩家輸入 ─────────
ACTIONS = [
    {"行動": "佯攻刀疤、同時用左手對阿青使眼色要他繞到背後", "目標": "scar", "隱蔽": True},
    {"行動": "抄起桌上油燈，舉向刀疤逼近威脅", "目標": "scar", "隱蔽": False},
    {"行動": "沉聲追問究竟是誰指使他來討這筆債", "目標": "scar", "隱蔽": False},
    {"行動": "穩住呼吸、退半步觀察刀疤破綻與火勢", "目標": None, "隱蔽": False},
    {"行動": "趁他被火逼退，短刃直取持刀手腕", "目標": "scar", "隱蔽": False},
]
REACTION = {"反應": "側身格擋並冷笑回敬，趁勢逼近半步"}


async def main():
    grok = GrokClient()
    s = new_tavern_session()

    banner("初始地面真相（裁決視角，含 gm 秘密）")
    print(engine.ground_truth(s))

    banner("各方迷霧視圖（檢查誰看得到什麼）")
    for cid in s.scene.在場:
        print(f"\n── {cid}（{s.角色卡[cid].名}）的視圖 ──")
        print(engine.build_view(s, cid))

    banner("開始逐拍推進")
    await flow.advance(grok, s)
    ai = 0
    while not s.結束 and s.回合數 < 11:
        p = s.pending or {}
        if p.get("type") == "player_action":
            act = ACTIONS[ai % len(ACTIONS)]
            ai += 1
            banner(f"▶ 玩家行動 #{ai}（第 {s.回合數} 拍）：{act['行動']}｜目標={act['目標']}｜隱蔽={act['隱蔽']}")
            await flow.submit_player_action(grok, s, act)
        elif p.get("type") == "player_reaction":
            banner(f"▶ 玩家回應（第 {s.回合數} 拍）｜來襲：{p.get('incoming','')}")
            await flow.submit_player_reaction(grok, s, REACTION)
        else:
            await flow.advance(grok, s)

    banner(f"結束（共 {s.回合數} 拍）｜結束原因：{s.結束}")
    print("\n【最終帳本】")
    print(engine.ground_truth(s))
    banner("各角色記憶與滾動摘要")
    for cid in s.scene.在場:
        print(f"\n[{cid}] 摘要：{s.摘要.get(cid) or '（尚未壓縮）'}")
        print(f"[{cid}] 近期記憶（{len(s.記憶.get(cid, []))} 條）：")
        for m in s.記憶.get(cid, []):
            print(f"   · {m[:60]}")

    await grok.close()


if __name__ == "__main__":
    asyncio.run(main())
