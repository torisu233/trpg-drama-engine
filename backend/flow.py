"""流程编排：逐拍推进 + 每拍维护（TTL/整理/summary）。

驱动方式（皆服务 Web 前后端）：
- advance：开局把场景推进到第一个玩家决策点（new_game 用，整段跑完不逐拍）
- stream_action / stream_reaction：玩家行动/反应后，每拍 yield 一次 session，端点逐拍推前端
共用 _resolve_beat / _advance_stream / 玩家拍 helper，逻辑单一不重复。
"""
from .grok_client import GrokClient
from .models import Session, Intent, Reaction
from . import engine, agents, config


def _incoming_desc(s: Session, intent: Intent) -> str:
    name = s.cards[intent.actor].name
    return f"{name}：{intent.action}"


def _incoming_for_player(s: Session, intent: Intent) -> str:
    """玩家被点名回应时看到的「来袭」描述。敌方**covert**行动不泄露真意——
    表象要等裁决才生成，此刻只给非揭示的预警；开放行动与我方行动照常给具体内容。"""
    card = s.cards.get(intent.actor)
    name = card.name if card else intent.actor
    ally = bool(card and card.faction == "ally")
    if getattr(intent, "covert", False) and not ally:
        return f"{name} 似有异动，正冲你而来"
    return f"{name}：{intent.action}"


# ───────────────── 每拍维护 ─────────────────
async def _consolidate_if(grok: GrokClient, s: Session, label: str, conds: list,
                          threshold: int = config.CONSOLIDATE_THRESHOLD) -> list:
    mergeable, keep = [], []
    for c in conds:
        if c.ttl is None and c.visibility == "public":
            mergeable.append(c)
        else:
            keep.append(c)
    if len(mergeable) < threshold:
        return conds
    merged = await agents.consolidate_conditions(grok, s, label, mergeable)
    return keep + merged


async def _maybe_consolidate(grok: GrokClient, s: Session) -> None:
    sc = s.ledger.scene
    # 场景三列保持高阈值（多条独立环境事实并存，降太低易误并）
    sc.social_facts = await _consolidate_if(grok, s, "social_facts/承诺/intel", sc.social_facts)
    sc.scene_facts = await _consolidate_if(grok, s, "scene_facts", sc.scene_facts)
    sc.spatial = await _consolidate_if(grok, s, "spatial", sc.spatial)
    # 角色身心状况：同一人状态易近义递进堆栈，用低阈值更早兜
    for cid, cl in s.ledger.characters.items():
        cl.conditions = await _consolidate_if(grok, s, f"{s.cards[cid].name} conditions",
                                            cl.conditions, threshold=config.CONSOLIDATE_THRESHOLD_STATE)


async def _maybe_compress(grok: GrokClient, s: Session) -> None:
    W = config.KEEP_RECENT
    for cid in s.scene.present:
        mem = s.memory.get(cid, [])
        if s.cards[cid].controller != "agent":
            if len(mem) > 2 * W:
                s.memory[cid] = mem[-2 * W:]
            continue
        if len(mem) >= 2 * W:
            evict, s.memory[cid] = mem[:W], mem[W:]
            s.summary[cid] = await agents.summarize_memory(grok, s, cid, s.summary.get(cid, ""), evict)


async def _resolve_beat(grok: GrokClient, s: Session, intent, reaction, actor, luck) -> None:
    adj = await agents.adjudicate(grok, s, intent, reaction, luck)
    engine.apply_delta(s, adj)
    narr = await agents.narrate(grok, s, adj, intent, reaction)
    engine.distribute(s, narr.public, narr.private)
    s.log.append(engine.log_action_entry(s, intent, reaction, actor, narr.public,
                                          cover=adj.cover, detected=adj.detected, time_skip=adj.time_skip))
    engine.consume_turn(s, actor)
    s.turn += 1
    engine.expire_transients(s)
    await _maybe_consolidate(grok, s)
    await _maybe_compress(grok, s)


# ───────────────── 玩家拍 ─────────────────
async def _player_action_beat(grok: GrokClient, s: Session, action: dict):
    """玩家行动拍（生成器）：玩家行动自己可见 → 先推一帧；队友回应可见也补帧，遮住裁决+narration。"""
    pid = engine.player_id(s)
    intent = Intent(actor=pid, **action)
    s.pending = None
    rtarget = engine.needs_reaction(s, intent)
    s.in_progress = engine.log_pending_entry(s, pid, intent)           # player=ally，行动文本可见
    yield s
    reaction = None
    if rtarget and rtarget != pid:
        reaction = await agents.character_reaction(grok, s, rtarget, _incoming_desc(s, intent))
        pend = engine.log_pending_entry(s, pid, intent, reaction)
        if pend["reaction_text"]:                                       # 队友回应可见 → 补帧
            s.in_progress = pend
            yield s
    luck = engine.roll_luck() if engine.is_contested(s, intent, rtarget) else None
    await _resolve_beat(grok, s, intent, reaction, pid, luck)
    s.in_progress = None
    yield s


async def _player_reaction_beat(grok: GrokClient, s: Session, reaction_payload: dict):
    """玩家回应拍（生成器）：玩家回应自己可见 → 先推一帧，遮住裁决+narration。"""
    p = s.pending or {}
    intent = Intent(**p.get("intent", {}))
    actor = p.get("actor", "")
    luck = p.get("luck")
    s.pending = None
    react = Reaction(actor=engine.player_id(s), **reaction_payload)
    s.in_progress = engine.log_pending_entry(s, actor, intent, react)  # 玩家回应可见（原行动者若我方其行动也可见）
    yield s
    await _resolve_beat(grok, s, intent, react, actor, luck)
    s.in_progress = None
    yield s


# ───────────────── time_skip（串流产生器） ─────────────────
async def _advance_stream(grok: GrokClient, s: Session):
    """逐个 NPC 拍推进，每拍 yield 一次 session；停在玩家决策点或结束时 yield 后返回。"""
    if s.ended:
        return
    pid = engine.player_id(s)
    while True:
        end = engine.check_end(s)
        if end:
            s.ended = end
            s.public_log.append(f"【场景结束】{end}")
            s.log.append(engine.log_system_entry(f"【场景结束】{end}"))
            yield s
            return
        actor = engine.pick_actor(s)
        if actor == pid:
            s.pending = {"type": "player_action"}
            yield s
            return
        intent = await agents.character_intent(grok, s, actor)
        rtarget = engine.needs_reaction(s, intent)
        if rtarget == pid:
            luck = engine.roll_luck() if engine.is_contested(s, intent, rtarget) else None
            s.pending = {
                "type": "player_reaction",
                "intent": intent.model_dump(),
                "actor": actor,
                "luck": luck,
                "incoming": _incoming_for_player(s, intent),
            }
            yield s
            return
        pend = engine.log_pending_entry(s, actor, intent)
        if pend["action_text"]:                       # 我方意图或敌方开放行动可见 → 提前显示，遮住后续
            s.in_progress = pend
            yield s
        reaction = None
        if rtarget:
            reaction = await agents.character_reaction(grok, s, rtarget, _incoming_desc(s, intent))
            pend = engine.log_pending_entry(s, actor, intent, reaction)
            if pend["reaction_text"]:                   # 我方回应可见 → 补帧
                s.in_progress = pend
                yield s
        luck = engine.roll_luck() if engine.is_contested(s, intent, rtarget) else None
        await _resolve_beat(grok, s, intent, reaction, actor, luck)
        s.in_progress = None
        yield s


# ───────────────── 开局推进（new_game 用，非串流） ─────────────────
async def advance(grok: GrokClient, s: Session) -> None:
    """把场景推进到第一个玩家决策点（开局尚无逐拍 UI，整段跑完）。"""
    async for _ in _advance_stream(grok, s):
        pass


# ───────────────── 串流（Web 游玩主路径） ─────────────────
async def stream_action(grok: GrokClient, s: Session, action: dict):
    async for _ in _player_action_beat(grok, s, action):
        yield s
    async for _ in _advance_stream(grok, s):
        yield s


async def stream_reaction(grok: GrokClient, s: Session, reaction: dict):
    async for _ in _player_reaction_beat(grok, s, reaction):
        yield s
    async for _ in _advance_stream(grok, s):
        yield s
