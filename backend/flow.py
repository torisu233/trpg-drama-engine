"""流程編排：逐拍推進 + 每拍維護（TTL/整理/摘要）。

驅動方式（皆服務 Web 前後端）：
- advance：開局把場景推進到第一個玩家決策點（new_game 用，整段跑完不逐拍）
- stream_action / stream_reaction：玩家行動/反應後，每拍 yield 一次 session，端點逐拍推前端
共用 _resolve_beat / _advance_stream / 玩家拍 helper，邏輯單一不重複。
"""
from .grok_client import GrokClient
from .models import Session, Intent, Reaction
from . import engine, agents, config
from .engine import PLAYER


def _incoming_desc(s: Session, intent: Intent) -> str:
    name = s.角色卡[intent.actor].名
    return f"{name}：{intent.行動}"


# ───────────────── 每拍維護 ─────────────────
async def _consolidate_if(grok: GrokClient, s: Session, label: str, conds: list) -> list:
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
    sc = s.會變層.場景
    sc.社會事實 = await _consolidate_if(grok, s, "社會事實/承諾/情報", sc.社會事實)
    sc.場景事實 = await _consolidate_if(grok, s, "場景事實", sc.場景事實)
    sc.空間關係 = await _consolidate_if(grok, s, "空間關係", sc.空間關係)
    for cid, cl in s.會變層.角色.items():
        cl.身心狀況 = await _consolidate_if(grok, s, f"{s.角色卡[cid].名} 身心狀況", cl.身心狀況)


async def _maybe_compress(grok: GrokClient, s: Session) -> None:
    W = config.KEEP_RECENT
    for cid in s.scene.在場:
        mem = s.記憶.get(cid, [])
        if s.角色卡[cid].扮演 != "agent":
            if len(mem) > 2 * W:
                s.記憶[cid] = mem[-2 * W:]
            continue
        if len(mem) >= 2 * W:
            evict, s.記憶[cid] = mem[:W], mem[W:]
            s.摘要[cid] = await agents.summarize_memory(grok, s, cid, s.摘要.get(cid, ""), evict)


async def _resolve_beat(grok: GrokClient, s: Session, intent, reaction, actor, luck) -> None:
    adj = await agents.adjudicate(grok, s, intent, reaction, luck)
    engine.apply_delta(s, adj)
    narr = await agents.narrate(grok, s, adj, intent, reaction)
    engine.distribute(s, narr.公開, narr.私密)
    engine.consume_turn(s, actor)
    s.回合數 += 1
    engine.expire_transients(s)
    await _maybe_consolidate(grok, s)
    await _maybe_compress(grok, s)


# ───────────────── 玩家拍 ─────────────────
async def _player_action_beat(grok: GrokClient, s: Session, action: dict) -> None:
    intent = Intent(actor=PLAYER, **action)
    s.pending = None
    rtarget = engine.needs_reaction(s, intent)
    reaction = None
    if rtarget and rtarget != PLAYER:
        reaction = await agents.character_reaction(grok, s, rtarget, _incoming_desc(s, intent))
    luck = engine.roll_luck() if engine.is_contested(s, intent, rtarget) else None
    await _resolve_beat(grok, s, intent, reaction, PLAYER, luck)


async def _player_reaction_beat(grok: GrokClient, s: Session, reaction_payload: dict) -> None:
    p = s.pending or {}
    intent = Intent(**p.get("intent", {}))
    actor = p.get("actor", "")
    luck = p.get("luck")
    s.pending = None
    react = Reaction(actor=PLAYER, **reaction_payload)
    await _resolve_beat(grok, s, intent, react, actor, luck)


# ───────────────── 推進（串流產生器） ─────────────────
async def _advance_stream(grok: GrokClient, s: Session):
    """逐個 NPC 拍推進，每拍 yield 一次 session；停在玩家決策點或結束時 yield 後返回。"""
    if s.結束:
        return
    while True:
        end = engine.check_end(s)
        if end:
            s.結束 = end
            s.公開日誌.append(f"【場景結束】{end}")
            yield s
            return
        actor = engine.pick_actor(s)
        if actor == PLAYER:
            s.pending = {"type": "player_action"}
            yield s
            return
        intent = await agents.character_intent(grok, s, actor)
        rtarget = engine.needs_reaction(s, intent)
        if rtarget == PLAYER:
            luck = engine.roll_luck() if engine.is_contested(s, intent, rtarget) else None
            s.pending = {
                "type": "player_reaction",
                "intent": intent.model_dump(),
                "actor": actor,
                "luck": luck,
                "incoming": _incoming_desc(s, intent),
            }
            yield s
            return
        reaction = None
        if rtarget:
            reaction = await agents.character_reaction(grok, s, rtarget, _incoming_desc(s, intent))
        luck = engine.roll_luck() if engine.is_contested(s, intent, rtarget) else None
        await _resolve_beat(grok, s, intent, reaction, actor, luck)
        yield s


# ───────────────── 開局推進（new_game 用，非串流） ─────────────────
async def advance(grok: GrokClient, s: Session) -> None:
    """把場景推進到第一個玩家決策點（開局尚無逐拍 UI，整段跑完）。"""
    async for _ in _advance_stream(grok, s):
        pass


# ───────────────── 串流（Web 遊玩主路徑） ─────────────────
async def stream_action(grok: GrokClient, s: Session, action: dict):
    await _player_action_beat(grok, s, action)
    yield s
    async for _ in _advance_stream(grok, s):
        yield s


async def stream_reaction(grok: GrokClient, s: Session, reaction: dict):
    await _player_reaction_beat(grok, s, reaction)
    yield s
    async for _ in _advance_stream(grok, s):
        yield s
