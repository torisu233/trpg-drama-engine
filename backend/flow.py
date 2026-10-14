"""Orchestration: advance beat by beat + per-beat upkeep (TTL/consolidation/summary).

Entry points (all serve the web frontend/backend):
- advance: at game start, push the scene to the first player decision point (used by new_game; runs to completion, not beat by beat)
- stream_action / stream_reaction: after a player action/reaction, yield the session once per beat so the endpoint can push each beat to the frontend
They share _resolve_beat / _advance_stream / the player-beat helpers, so the logic exists once.
"""
from .llm_client import LLMClient
from .models import Session, Intent, Reaction
from . import engine, agents, config


def _incoming_desc(s: Session, intent: Intent) -> str:
    name = s.cards[intent.actor].name
    return f"{name}: {intent.action}"


def _incoming_for_player(s: Session, intent: Intent) -> str:
    """The "incoming" description the player sees when called on to react. An enemy **covert** action does not leak
    its true intent — the cover is only generated at adjudication, so for now give a non-revealing warning; open and
    ally actions show their actual content as usual."""
    card = s.cards.get(intent.actor)
    name = card.name if card else intent.actor
    ally = bool(card and card.faction == "ally")
    if getattr(intent, "covert", False) and not ally:
        return f"{name} seems to be up to something, and it's aimed at you"
    return f"{name}: {intent.action}"


# ───────────────── per-beat upkeep ─────────────────
async def _consolidate_if(llm: LLMClient, s: Session, label: str, conds: list,
                          threshold: int = config.CONSOLIDATE_THRESHOLD) -> list:
    mergeable, keep = [], []
    for c in conds:
        if c.ttl is None and c.visibility == "public":
            mergeable.append(c)
        else:
            keep.append(c)
    if len(mergeable) < threshold:
        return conds
    merged = await agents.consolidate_conditions(llm, s, label, mergeable)
    return keep + merged


async def _maybe_consolidate(llm: LLMClient, s: Session) -> None:
    sc = s.ledger.scene
    # the three scene lists keep a high threshold (many independent environment facts coexist; too low over-merges)
    sc.social_facts = await _consolidate_if(llm, s, "social_facts/promises/intel", sc.social_facts)
    sc.scene_facts = await _consolidate_if(llm, s, "scene_facts", sc.scene_facts)
    sc.spatial = await _consolidate_if(llm, s, "spatial", sc.spatial)
    # character conditions: one person's state tends to stack near-duplicate escalations, so use a lower threshold
    for cid, cl in s.ledger.characters.items():
        cl.conditions = await _consolidate_if(llm, s, f"{s.cards[cid].name} conditions",
                                            cl.conditions, threshold=config.CONSOLIDATE_THRESHOLD_STATE)


async def _maybe_compress(llm: LLMClient, s: Session) -> None:
    W = config.KEEP_RECENT
    for cid in s.scene.present:
        mem = s.memory.get(cid, [])
        if s.cards[cid].controller != "agent":
            if len(mem) > 2 * W:
                s.memory[cid] = mem[-2 * W:]
            continue
        if len(mem) >= 2 * W:
            evict, s.memory[cid] = mem[:W], mem[W:]
            s.summary[cid] = await agents.summarize_memory(llm, s, cid, s.summary.get(cid, ""), evict)


async def _resolve_beat(llm: LLMClient, s: Session, intent, reaction, actor, luck) -> None:
    adj = await agents.adjudicate(llm, s, intent, reaction, luck)
    engine.apply_delta(s, adj)
    narr = await agents.narrate(llm, s, adj, intent, reaction)
    engine.distribute(s, narr.public, narr.private)
    s.log.append(engine.log_action_entry(s, intent, reaction, actor, narr.public,
                                          cover=adj.cover, detected=adj.detected, time_skip=adj.time_skip))
    engine.consume_turn(s, actor)
    s.turn += 1
    engine.expire_transients(s)
    await _maybe_consolidate(llm, s)
    await _maybe_compress(llm, s)


# ───────────────── player beats ─────────────────
async def _player_action_beat(llm: LLMClient, s: Session, action: dict):
    """Player action beat (generator): the player's own action is visible → push a frame first; a visible teammate reaction gets an extra frame; adjudication + narration stay hidden until done."""
    pid = engine.player_id(s)
    intent = Intent(actor=pid, **action)
    s.pending = None
    rtarget = engine.needs_reaction(s, intent)
    s.in_progress = engine.log_pending_entry(s, pid, intent)           # player = ally, action text visible
    yield s
    reaction = None
    if rtarget and rtarget != pid:
        reaction = await agents.character_reaction(llm, s, rtarget, _incoming_desc(s, intent))
        pend = engine.log_pending_entry(s, pid, intent, reaction)
        if pend["reaction_text"]:                                       # teammate reaction visible → extra frame
            s.in_progress = pend
            yield s
    luck = engine.roll_luck() if engine.is_contested(s, intent, rtarget) else None
    await _resolve_beat(llm, s, intent, reaction, pid, luck)
    s.in_progress = None
    yield s


async def _player_reaction_beat(llm: LLMClient, s: Session, reaction_payload: dict):
    """Player reaction beat (generator): the player's own reaction is visible → push a frame first; adjudication + narration stay hidden until done."""
    p = s.pending or {}
    intent = Intent(**p.get("intent", {}))
    actor = p.get("actor", "")
    luck = p.get("luck")
    s.pending = None
    react = Reaction(actor=engine.player_id(s), **reaction_payload)
    s.in_progress = engine.log_pending_entry(s, actor, intent, react)  # player reaction visible (the original actor's action too, if ally)
    yield s
    await _resolve_beat(llm, s, intent, react, actor, luck)
    s.in_progress = None
    yield s


# ───────────────── advancing (streaming generator) ─────────────────
async def _advance_stream(llm: LLMClient, s: Session):
    """Advance NPC beats one at a time, yielding the session once per beat; yields and returns at a player decision point or the end."""
    if s.ended:
        return
    pid = engine.player_id(s)
    while True:
        end = engine.check_end(s)
        if end:
            s.ended = end
            s.public_log.append(f"[Scene Over] {end}")
            s.log.append(engine.log_system_entry(f"[Scene Over] {end}"))
            yield s
            return
        actor = engine.pick_actor(s)
        if actor == pid:
            s.pending = {"type": "player_action"}
            yield s
            return
        intent = await agents.character_intent(llm, s, actor)
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
        if pend["action_text"]:                       # ally intent or open enemy action is visible → show early, hide what follows
            s.in_progress = pend
            yield s
        reaction = None
        if rtarget:
            reaction = await agents.character_reaction(llm, s, rtarget, _incoming_desc(s, intent))
            pend = engine.log_pending_entry(s, actor, intent, reaction)
            if pend["reaction_text"]:                   # ally reaction visible → extra frame
                s.in_progress = pend
                yield s
        luck = engine.roll_luck() if engine.is_contested(s, intent, rtarget) else None
        await _resolve_beat(llm, s, intent, reaction, actor, luck)
        s.in_progress = None
        yield s


# ───────────────── game-start advance (used by new_game, not streamed) ─────────────────
async def advance(llm: LLMClient, s: Session) -> None:
    """Push the scene to the first player decision point (there is no per-beat UI at game start yet, so run to completion)."""
    async for _ in _advance_stream(llm, s):
        pass


# ───────────────── streaming (main web play path) ─────────────────
async def stream_action(llm: LLMClient, s: Session, action: dict):
    async for _ in _player_action_beat(llm, s, action):
        yield s
    async for _ in _advance_stream(llm, s):
        yield s


async def stream_reaction(llm: LLMClient, s: Session, reaction: dict):
    async for _ in _player_reaction_beat(llm, s, reaction):
        yield s
    async for _ in _advance_stream(llm, s):
        yield s
