"""流程编排：逐拍推进 + 每拍维护（TTL/整理/摘要）。

驱动方式（皆服务 Web 前后端）：
- advance：开局把场景推进到第一个玩家决策点（new_game 用，整段跑完不逐拍）
- stream_action / stream_reaction：玩家行动/反应后，每拍 yield 一次 session，端点逐拍推前端
共用 _resolve_beat / _advance_stream / 玩家拍 helper，逻辑单一不重复。
"""
from .grok_client import GrokClient
from .models import Session, Intent, Reaction
from . import engine, agents, config
from .engine import PLAYER


def _incoming_desc(s: Session, intent: Intent) -> str:
    name = s.角色卡[intent.actor].名
    return f"{name}：{intent.行动}"


# ───────────────── 每拍维护 ─────────────────
async def _consolidate_if(grok: GrokClient, s: Session, label: str, conds: list) -> list:
    mergeable, keep = [], []
    for c in conds:
        if c.剩余拍数 is None and c.可见性 == "public":
            mergeable.append(c)
        else:
            keep.append(c)
    if len(mergeable) < config.CONSOLIDATE_THRESHOLD:
        return conds
    merged = await agents.consolidate_conditions(grok, s, label, mergeable)
    return keep + merged


async def _maybe_consolidate(grok: GrokClient, s: Session) -> None:
    sc = s.会变层.场景
    sc.社会事实 = await _consolidate_if(grok, s, "社会事实/承诺/情报", sc.社会事实)
    sc.场景事实 = await _consolidate_if(grok, s, "场景事实", sc.场景事实)
    sc.空间关系 = await _consolidate_if(grok, s, "空间关系", sc.空间关系)
    for cid, cl in s.会变层.角色.items():
        cl.身心状况 = await _consolidate_if(grok, s, f"{s.角色卡[cid].名} 身心状况", cl.身心状况)


async def _maybe_compress(grok: GrokClient, s: Session) -> None:
    W = config.KEEP_RECENT
    for cid in s.scene.在场:
        mem = s.记忆.get(cid, [])
        if s.角色卡[cid].扮演 != "agent":
            if len(mem) > 2 * W:
                s.记忆[cid] = mem[-2 * W:]
            continue
        if len(mem) >= 2 * W:
            evict, s.记忆[cid] = mem[:W], mem[W:]
            s.摘要[cid] = await agents.summarize_memory(grok, s, cid, s.摘要.get(cid, ""), evict)


async def _resolve_beat(grok: GrokClient, s: Session, intent, reaction, actor, luck) -> None:
    adj = await agents.adjudicate(grok, s, intent, reaction, luck)
    engine.apply_delta(s, adj)
    narr = await agents.narrate(grok, s, adj, intent, reaction)
    engine.distribute(s, narr.公开, narr.私密)
    s.日志.append(engine.log_action_entry(s, intent, reaction, actor, narr.公开))
    engine.consume_turn(s, actor)
    s.回合数 += 1
    engine.expire_transients(s)
    await _maybe_consolidate(grok, s)
    await _maybe_compress(grok, s)


# ───────────────── 玩家拍 ─────────────────
async def _player_action_beat(grok: GrokClient, s: Session, action: dict):
    """玩家行动拍（生成器）：玩家行动自己可见 → 先推一帧；队友回应可见也补帧，遮住裁决+叙事。"""
    intent = Intent(actor=PLAYER, **action)
    s.pending = None
    rtarget = engine.needs_reaction(s, intent)
    s.进行中 = engine.log_pending_entry(s, PLAYER, intent)        # 玩家=我方，行动文本可见
    yield s
    reaction = None
    if rtarget and rtarget != PLAYER:
        reaction = await agents.character_reaction(grok, s, rtarget, _incoming_desc(s, intent))
        pend = engine.log_pending_entry(s, PLAYER, intent, reaction)
        if pend["反应文本"]:                                       # 队友回应可见 → 补帧
            s.进行中 = pend
            yield s
    luck = engine.roll_luck() if engine.is_contested(s, intent, rtarget) else None
    await _resolve_beat(grok, s, intent, reaction, PLAYER, luck)
    s.进行中 = None
    yield s


async def _player_reaction_beat(grok: GrokClient, s: Session, reaction_payload: dict):
    """玩家回应拍（生成器）：玩家回应自己可见 → 先推一帧，遮住裁决+叙事。"""
    p = s.pending or {}
    intent = Intent(**p.get("intent", {}))
    actor = p.get("actor", "")
    luck = p.get("luck")
    s.pending = None
    react = Reaction(actor=PLAYER, **reaction_payload)
    s.进行中 = engine.log_pending_entry(s, actor, intent, react)  # 玩家回应可见（原行动者若我方其行动也可见）
    yield s
    await _resolve_beat(grok, s, intent, react, actor, luck)
    s.进行中 = None
    yield s


# ───────────────── 推进（串流产生器） ─────────────────
async def _advance_stream(grok: GrokClient, s: Session):
    """逐个 NPC 拍推进，每拍 yield 一次 session；停在玩家决策点或结束时 yield 后返回。"""
    if s.结束:
        return
    while True:
        end = engine.check_end(s)
        if end:
            s.结束 = end
            s.公开日志.append(f"【场景结束】{end}")
            s.日志.append(engine.log_system_entry(f"【场景结束】{end}"))
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
        pend = engine.log_pending_entry(s, actor, intent)
        if pend["行动文本"]:                       # 我方意图可见 → 提前显示，遮住后续
            s.进行中 = pend
            yield s
        reaction = None
        if rtarget:
            reaction = await agents.character_reaction(grok, s, rtarget, _incoming_desc(s, intent))
            pend = engine.log_pending_entry(s, actor, intent, reaction)
            if pend["反应文本"]:                   # 我方回应可见 → 补帧
                s.进行中 = pend
                yield s
        luck = engine.roll_luck() if engine.is_contested(s, intent, rtarget) else None
        await _resolve_beat(grok, s, intent, reaction, actor, luck)
        s.进行中 = None
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
