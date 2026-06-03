"""流程編排：推進迴圈 + 玩家行動/反應的注入點。

迴圈在兩種情況停下等玩家：
1. player_action  —— 行動條輪到玩家
2. player_reaction —— 玩家被某 NPC 鎖定為攻擊目標，須先反應
"""
from typing import Optional
from .grok_client import GrokClient
from .models import Session, Intent, Reaction
from . import engine, agents
from .engine import PLAYER


def _incoming_desc(s: Session, intent: Intent) -> str:
    name = s.角色卡[intent.actor].名
    return f"{name} {intent.行動}" + (f"：{intent.方式}" if intent.方式 else "")


async def _resolve(grok: GrokClient, s: Session, intent: Intent,
                   reaction: Optional[Reaction], actor: str) -> None:
    """收齊意圖(+反應)後，跑裁決→套用→敘事→分發→扣行動條。"""
    rtarget = engine.needs_reaction(s, intent)
    luck = engine.roll_luck() if engine.is_contested(s, intent, rtarget) else None
    adj = await agents.adjudicate(grok, s, intent, reaction, luck)
    engine.apply_delta(s, adj)
    narr = await agents.narrate(grok, s, adj, intent)
    engine.distribute(s, narr.公開, narr.私密)
    engine.consume_turn(s, actor)
    s.回合數 += 1


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

        # NPC 出意圖
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

        # 對 NPC 或無對象：必要時收 NPC 反應，直接結算
        reaction = None
        if rtarget:
            reaction = await agents.character_reaction(grok, s, rtarget, _incoming_desc(s, intent))
        # _resolve 內會自行擲運氣（依兩軸）
        # 但反應已收，需用同一套；直接呼叫裁決流程：
        luck = engine.roll_luck() if engine.is_contested(s, intent, rtarget) else None
        adj = await agents.adjudicate(grok, s, intent, reaction, luck)
        engine.apply_delta(s, adj)
        narr = await agents.narrate(grok, s, adj, intent)
        engine.distribute(s, narr.公開, narr.私密)
        engine.consume_turn(s, actor)
        s.回合數 += 1


async def submit_player_action(grok: GrokClient, s: Session, action: dict) -> None:
    intent = Intent(actor=PLAYER, **action)
    s.pending = None
    rtarget = engine.needs_reaction(s, intent)
    reaction = None
    if rtarget and rtarget != PLAYER:
        reaction = await agents.character_reaction(grok, s, rtarget, _incoming_desc(s, intent))
    luck = engine.roll_luck() if engine.is_contested(s, intent, rtarget) else None
    adj = await agents.adjudicate(grok, s, intent, reaction, luck)
    engine.apply_delta(s, adj)
    narr = await agents.narrate(grok, s, adj, intent)
    engine.distribute(s, narr.公開, narr.私密)
    engine.consume_turn(s, PLAYER)
    s.回合數 += 1
    await advance(grok, s)


async def submit_player_reaction(grok: GrokClient, s: Session, reaction: dict) -> None:
    p = s.pending or {}
    intent = Intent(**p.get("intent", {}))
    actor = p.get("actor", "")
    luck = p.get("luck")
    s.pending = None
    react = Reaction(actor=PLAYER, **reaction)
    adj = await agents.adjudicate(grok, s, intent, react, luck)
    engine.apply_delta(s, adj)
    narr = await agents.narrate(grok, s, adj, intent)
    engine.distribute(s, narr.公開, narr.私密)
    engine.consume_turn(s, actor)
    s.回合數 += 1
    await advance(grok, s)
