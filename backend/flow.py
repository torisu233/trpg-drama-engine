"""流程編排：推進迴圈 + 玩家行動/反應的注入點 + 每拍維護（TTL 過期、滾動摘要）。

迴圈在兩種情況停下等玩家：
1. player_action  —— 行動條輪到玩家
2. player_reaction —— 玩家被某 NPC 鎖定為攻擊目標，須先反應
"""
from typing import Optional
from .grok_client import GrokClient
from .models import Session, Intent, Reaction
from . import engine, agents, config
from .engine import PLAYER


def _incoming_desc(s: Session, intent: Intent) -> str:
    name = s.角色卡[intent.actor].名
    return f"{name}：{intent.行動}"


async def _consolidate_if(grok: GrokClient, s: Session, label: str, conds: list) -> list:
    """只整理「公開且持久」的條目；gm/self/faction/帶 TTL 的瞬態一律保留不動。"""
    mergeable, keep = [], []
    for c in conds:
        if c.剩餘拍數 is None and c.可見性 == "public":
            mergeable.append(c)
        else:
            keep.append(c)
    if len(mergeable) < config.CONSOLIDATE_THRESHOLD:
        return conds
    merged = await agents.consolidate_conditions(grok, s, label, mergeable)
    return keep + merged


async def _maybe_consolidate(grok: GrokClient, s: Session) -> None:
    """帳本整理 pass：合併近義條目、清冗餘，根治重複累積。"""
    sc = s.會變層.場景
    sc.社會事實 = await _consolidate_if(grok, s, "社會事實/承諾/情報", sc.社會事實)
    sc.場景事實 = await _consolidate_if(grok, s, "場景事實", sc.場景事實)
    sc.空間關係 = await _consolidate_if(grok, s, "空間關係", sc.空間關係)
    for cid, cl in s.會變層.角色.items():
        cl.身心狀況 = await _consolidate_if(grok, s, f"{s.角色卡[cid].名} 身心狀況", cl.身心狀況)


async def _maybe_compress(grok: GrokClient, s: Session) -> None:
    """滾動摘要：某 AI 角色記憶達 2W 時，把最舊 W 條摺進摘要。"""
    W = config.KEEP_RECENT
    for cid in s.scene.在場:
        mem = s.記憶.get(cid, [])
        if s.角色卡[cid].扮演 != "agent":
            if len(mem) > 2 * W:                       # 人類玩家：不摘要，僅截斷（未注入，省記憶體）
                s.記憶[cid] = mem[-2 * W:]
            continue
        if len(mem) >= 2 * W:
            evict, s.記憶[cid] = mem[:W], mem[W:]
            s.摘要[cid] = await agents.summarize_memory(
                grok, s, cid, s.摘要.get(cid, ""), evict)


async def _resolve_beat(grok: GrokClient, s: Session, intent: Intent,
                        reaction: Optional[Reaction], actor: str,
                        luck: Optional[str]) -> None:
    """收齊意圖(+反應+運氣)後：裁決→套用→敘事→分發→扣行動條→每拍維護。"""
    adj = await agents.adjudicate(grok, s, intent, reaction, luck)
    engine.apply_delta(s, adj)
    narr = await agents.narrate(grok, s, adj, intent, reaction)
    engine.distribute(s, narr.公開, narr.私密)
    engine.consume_turn(s, actor)
    s.回合數 += 1
    engine.expire_transients(s)          # 帳本清理：瞬態 TTL 過期
    await _maybe_consolidate(grok, s)     # 帳本整理：合併近義、清冗餘
    await _maybe_compress(grok, s)        # 滾動摘要


async def advance(grok: GrokClient, s: Session) -> None:
    """推進到下一個需要玩家輸入的點，或場景結束。"""
    if s.結束:
        return
    while True:
        end = engine.check_end(s)
        if end:
            s.結束 = end
            s.公開日誌.append(f"【場景結束】{end}")
            return

        actor = engine.pick_actor(s)
        if actor == PLAYER:
            s.pending = {"type": "player_action"}
            return

        intent = await agents.character_intent(grok, s, actor)
        rtarget = engine.needs_reaction(s, intent)

        if rtarget == PLAYER:
            # 須先向玩家收反應 → 停下，把來襲威脅丟給玩家
            luck = engine.roll_luck() if engine.is_contested(s, intent, rtarget) else None
            s.pending = {
                "type": "player_reaction",
                "intent": intent.model_dump(),
                "actor": actor,
                "luck": luck,
                "incoming": _incoming_desc(s, intent),
            }
            return

        reaction = None
        if rtarget:
            reaction = await agents.character_reaction(grok, s, rtarget, _incoming_desc(s, intent))
        luck = engine.roll_luck() if engine.is_contested(s, intent, rtarget) else None
        await _resolve_beat(grok, s, intent, reaction, actor, luck)


async def submit_player_action(grok: GrokClient, s: Session, action: dict) -> None:
    intent = Intent(actor=PLAYER, **action)
    s.pending = None
    rtarget = engine.needs_reaction(s, intent)
    reaction = None
    if rtarget and rtarget != PLAYER:
        reaction = await agents.character_reaction(grok, s, rtarget, _incoming_desc(s, intent))
    luck = engine.roll_luck() if engine.is_contested(s, intent, rtarget) else None
    await _resolve_beat(grok, s, intent, reaction, PLAYER, luck)
    await advance(grok, s)


async def submit_player_reaction(grok: GrokClient, s: Session, reaction: dict) -> None:
    p = s.pending or {}
    intent = Intent(**p.get("intent", {}))
    actor = p.get("actor", "")
    luck = p.get("luck")
    s.pending = None
    react = Reaction(actor=PLAYER, **reaction)
    await _resolve_beat(grok, s, intent, react, actor, luck)
    await advance(grok, s)
