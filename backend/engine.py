"""内核引擎（纯逻辑，none API）：action_bar、两轴判定、迷雾过滤、delta 套用。

这些都是可单测的纯函数；agent 调用在 agents.py，流程编排在 flow.py。
"""
import random
from typing import List, Optional, Tuple
from .models import Session, Condition, DeltaItem, LedgerDelta, Adjudication
from . import config

PLAYER = "player"

# 触发「无法反应 / 失能」的关键字
INCAPACITATED_KW = ("昏迷", "失去意识", "绑", "缚", "瘫", "晕", "制伏", "压制")
# 环境争议关键字（无对手仍是赌注）
RISKY_KW = ("跳", "攀", "潜", "赌", "抢", "翻越", "扑", "闪身")


def resolve_id(s: Session, key) -> Optional[str]:
    """把 LLM 给的角色「名字或 id」解析回 char_id。

    设计：agent 一律看/用角色名，程序只在操作边界用本函数转回 id。
    兼容三种输入：已是 id → 原样；是某角色的「name」→ 该 id；都不匹配 → None。"""
    if not key:
        return None
    if key in s.cards:                       # 已是 id
        return key
    for cid, c in s.cards.items():            # 按名字匹配（名字应唯一）
        if c.name == key:
            return cid
    return None


def player_id(s: Session) -> str:
    """玩家角色 id：靠语义字段「controller==player」识别，**不依赖写死的 id**。找不到则兜底回 PLAYER。"""
    for cid, c in s.cards.items():
        if c.controller == "player":
            return cid
    return PLAYER


def prune_orphans(s: Session) -> None:
    """剔除「present / ledger」里引用了不存在角色卡的孤儿 id（就地修改）。

    保证不变量「present ⊆ cards」「ledger.角色键 ⊆ cards」，杜绝下游各处裸 `s.cards[cid]`
    （ground_truth / build_view / flow 维护…）因不一致剧本而 KeyError。开局与读档两个入口都调。"""
    s.scene.present = [cid for cid in s.scene.present if cid in s.cards]
    s.ledger.characters = {cid: cl for cid, cl in s.ledger.characters.items() if cid in s.cards}


def validate_playable(s: Session) -> Optional[str]:
    """开局前的可玩性校验：返回「不可玩的原因」字符串，可玩则 None。

    把两类会让 new_game 崩/挂的不完整剧本，挡成清晰的拒绝（而非 500 或无限循环）：
      ① 无任何有行动条的角色 → pick_actor 无人可动（原会 ValueError→500）。
      ② none「controller==player」或玩家不在场 → advance 永远轮不到玩家、停不下来（原会无限 LLM 循环）。
    """
    if not s.ledger.characters:
        return "没有任何在场角色（请在场景「present」里至少放一个角色）"
    players = [cid for cid, c in s.cards.items() if c.controller == "player"]
    if not players:
        return "缺少玩家角色（需把某个角色的「controller」设为「player」）"
    if not any(pid in s.ledger.characters for pid in players):
        return "玩家角色不在场（请把玩家角色加入场景「present」）"
    return None


# ───────────────── action_bar ─────────────────
def _tick(s: Session) -> None:
    for cl in s.ledger.characters.values():
        cl.gauge += cl.speed


def pick_actor(s: Session) -> str:
    """每次调用先 +1 拍；没人达门槛就继续加，直到有人达标。返回行动者 id。"""
    actors = s.ledger.characters
    if not actors:                            # 无人有初始局面 → 否则下面会死循环
        raise ValueError("无可行动角色：ledger.角色为空（剧本缺初始局面）")
    _tick(s)  # 「场上每行动一次，大家加一次」
    safety = 0
    while not any(cl.gauge >= config.ACTION_THRESHOLD for cl in actors.values()):
        _tick(s)
        safety += 1
        if safety > 100000:                   # 兜底：全员速度<=0 等异常，绝不死循环
            break
    ready = [cid for cid, cl in actors.items()
             if cl.gauge >= config.ACTION_THRESHOLD]
    if not ready:                             # 没人达门槛（异常）→ 取行动值最高者兜底
        ready = [max(actors, key=lambda c: actors[c].gauge)]
    # 纯按行动值排序：高者先动；相同则不额外排序，取在场/字典的自然顺序
    # （max 在并列时返回首个最大值，故等同自然顺序——不再让玩家无条件优先）
    return max(ready, key=lambda c: actors[c].gauge)


def consume_turn(s: Session, actor: str) -> None:
    s.ledger.characters[actor].gauge -= config.ACTION_THRESHOLD   # 扣门槛、保留溢出


def beats_to_act(cl, threshold: int = config.ACTION_THRESHOLD) -> int:
    """还差几拍这个角色才到行动门槛（程序算好；负初始行动值→很多拍后，模拟缓慢逼近）。"""
    速 = max(cl.speed, 1)
    需 = max(threshold - cl.gauge, 0)
    return (需 + 速 - 1) // 速


def action_order(s: Session) -> list:
    """在场角色按「还有几拍轮到」升序：[(cid, name, faction, beats)…]。供 agent 了解行动次序与逼近。"""
    rows = []
    for cid in s.scene.present:
        cl = s.ledger.characters.get(cid)
        if cl is None or cid not in s.cards:
            continue
        rows.append((cid, s.cards[cid].name, s.cards[cid].faction, beats_to_act(cl)))
    rows.sort(key=lambda t: (t[3], -s.ledger.characters[t[0]].gauge))
    return rows


# ───────────────── 感知 / 两轴 ─────────────────
def _perceives(s: Session, who: str) -> bool:
    cap = s.ledger.characters[who].perception
    return not any(k in cap for k in ("昏迷", "失去意识"))


def _can_oppose(s: Session, who: str) -> bool:
    cl = s.ledger.characters[who]
    if any(k in cl.perception for k in ("昏迷", "失去意识")):
        return False
    blob = " ".join(c.content for c in cl.status_effects)
    return not any(k in blob for k in INCAPACITATED_KW)


def target_char(s: Session, intent) -> Optional[str]:
    t = resolve_id(s, intent.target)            # 目标可能是名字或 id，统一解析回 id
    if t and t in s.ledger.characters and t != intent.actor:
        return t
    return None


def needs_reaction(s: Session, intent) -> Optional[str]:
    """轴 A：是否该向某角色收反应？返回该角色 id 或 None。
    闸门：对方是角色 ∧（是玩家 ∨（感知得到 ∧ 能对抗））。模棱两可宁可多收。"""
    tgt = target_char(s, intent)
    if not tgt:
        return None
    if tgt == player_id(s):
        return tgt                          # 对玩家一定收
    if _perceives(s, tgt) and _can_oppose(s, tgt):
        return tgt
    return None


def is_contested(s: Session, intent, reaction_target: Optional[str]) -> bool:
    """轴 B：是否争议（掷运气）？被主动对抗 或 环境本身是赌注。"""
    if reaction_target:
        return True
    return any(k in (intent.action or "") for k in RISKY_KW)


def roll_luck() -> str:
    return random.choices(config.LUCK_TIERS, weights=config.LUCK_WEIGHTS, k=1)[0]


# ───────────────── 迷雾：产出某角色可见的视图文字 ─────────────────
def _visible(cond: Condition, viewer: str, faction: str) -> bool:
    v = cond.visibility
    if v == "public":
        return True
    if v == "gm":
        return False
    if v.startswith("faction:"):
        return v.split(":", 1)[1] == faction
    if v.startswith("self:"):
        return v.split(":", 1)[1] == viewer
    return True


def _fmt_conds(conds: List[Condition], viewer: str, faction: str) -> List[str]:
    out = []
    for c in conds:
        if not _visible(c, viewer, faction):
            continue
        g = f"（{c.gates}）" if c.gates else ""
        d = f"[{c.severity}]" if c.severity else ""
        out.append(f"{c.content}{d}{g}")
    return out


def build_view(s: Session, viewer: str) -> str:
    """组出 viewer 能看到的局面文字（喂给角色 agent）。维持迷雾。"""
    faction = s.cards[viewer].faction
    lines = [f"【scene】{s.scene.location}"]

    # 场景公开事实
    facts = _fmt_conds(s.ledger.scene.scene_facts, viewer, faction) \
        + _fmt_conds(s.ledger.scene.spatial, viewer, faction)
    if facts:
        lines.append("【surroundings】" + "；".join(facts))
    social = _fmt_conds(s.ledger.scene.social_facts, viewer, faction)
    if social:
        lines.append("【约定/intel】" + "；".join(social))

    # 各角色（自己看全部；别人只看公开＋可见）
    for cid, cl in s.ledger.characters.items():
        if cid not in s.scene.present:
            continue
        card = s.cards[cid]
        g = f"，{card.gender}" if card.gender else ""
        self_mark = "·本人" if cid == viewer else ""   # 不用「你」——「你」留给叙事专指主角玩家
        seg = [f"{card.name}（{card.faction}{g}{self_mark}）：{cl.posture or 'present'}"]
        body = _fmt_conds(cl.conditions, viewer, faction) + _fmt_conds(cl.status_effects, viewer, faction)
        if cid == viewer:                    # 自己能看到自己的随身与物品
            body += _fmt_conds(cl.carried, viewer, faction)
            if cl.items:
                body.append("inventory：" + "、".join(f"{it.name}({it.state})" for it in cl.items.values()))
        if body:
            seg.append("，".join(body))
        lines.append(" ".join(seg))

    # 阵营私有计策
    plans = s.ledger.faction_private.get(faction, {}).get("plans", [])
    if plans:
        lines.append("【我方计策】" + "；".join(plans))

    return "\n".join(lines)


def player_situation(s: Session, viewer: Optional[str] = None) -> dict:
    """玩家可见的环境与社会面（迷雾过滤）：scene/surroundings/约定情报/我方计策。结构化给前端。"""
    viewer = viewer or player_id(s)
    fac = s.cards[viewer].faction
    sc = s.ledger.scene
    return {
        "scene": s.scene.location,
        "surroundings": _fmt_conds(sc.scene_facts, viewer, fac) + _fmt_conds(sc.spatial, viewer, fac),
        "intel": _fmt_conds(sc.social_facts, viewer, fac),
        "plans": list(s.ledger.faction_private.get(fac, {}).get("plans", [])),
    }


def known_characters(s: Session, viewer: Optional[str] = None) -> list:
    """玩家所知的在场角色（结构化）。
    - 同阵营（含自己）：给完整角色卡——abilities/防御/weaknesses/动机等，对队友本就知情。
    - 敌方：只给可见状态——底细是要靠观察发现的秘密，不注入。
    """
    viewer = viewer or player_id(s)
    fac = s.cards[viewer].faction
    out = []
    for cid in s.scene.present:
        cl = s.ledger.characters.get(cid)
        if cid not in s.cards or cl is None:
            continue
        card = s.cards[cid]
        ally = card.faction == fac
        item = {
            "id": cid, "name": card.name, "faction": card.faction, "gender": card.gender,
            "is_self": cid == viewer, "is_ally": ally,
            "posture": cl.posture, "speed": cl.speed, "perception": cl.perception,
            "state": _fmt_conds(cl.conditions, viewer, fac) + _fmt_conds(cl.status_effects, viewer, fac),
        }
        if ally:                                  # 我方互知底细
            item.update({
                "backstory": card.backstory, "personality": card.personality, "voice": card.voice,
                "motive": card.motive, "tactics": card.tactics,
                "abilities": card.abilities, "defenses": card.defenses, "weaknesses": card.weaknesses,
            })
            if cid == viewer and cl.items:         # 自己看得到随身物品
                item["inventory"] = [f"{it.name}（{it.state}）" for it in cl.items.values()]
        out.append(item)
    return out


def faction_mates(s: Session, cid: str) -> List[str]:
    """与 cid 同阵营、在场的其他角色 id（同阵营互看整张卡用；跨阵营不含）。"""
    me = s.cards.get(cid)
    if not me:
        return []
    return [oid for oid in s.scene.present
            if oid != cid and oid in s.cards and s.cards[oid].faction == me.faction]


def ground_truth(s: Session) -> str:
    """给裁决的完整地面真相（全可见，含 gm 秘密）。"""
    lines = [f"【scene】{s.scene.location}"]
    for c in s.ledger.scene.scene_facts + s.ledger.scene.spatial + s.ledger.scene.social_facts:
        tag = "" if c.visibility == "public" else f" <{c.visibility}>"
        g = f"（{c.gates}）" if c.gates else ""
        lines.append(f"- {c.content}{g}{tag}")
    for cid, cl in s.ledger.characters.items():
        card = s.cards.get(cid)
        if card is None:                      # 防御：孤儿会变层条目（prune_orphans 已清，双保险，护住裁决主路径）
            continue
        g = f"/{card.gender}" if card.gender else ""
        lines.append(f"◆ {card.name}（{card.faction}{g}）速度{cl.speed} 感知:{cl.perception}")
        if card.abilities:
            lines.append(f"  abilities：{'、'.join(card.abilities)}")
        if card.defenses:
            lines.append(f"  defenses：{'、'.join(card.defenses)}")
        if card.weaknesses:
            lines.append(f"  weaknesses：{'、'.join(card.weaknesses)}")
        lines.append(f"  posture：{cl.posture}")
        for c in cl.conditions + cl.status_effects + cl.carried:
            tag = "" if c.visibility == "public" else f" <{c.visibility}>"
            g = f"（{c.gates}）" if c.gates else ""
            lines.append(f"  - {c.content}{g}{tag}")
        for it in cl.items.values():
            lines.append(f"  - items {it.name}：{it.state}，{it.location}")
    return "\n".join(lines)


# ───────────────── 套用裁决 delta（防御式，绝不崩） ─────────────────
def _normalize_vis(s: Session, vis: str) -> str:
    """visibility self:<X> 里 X 可能是名字（agent 用名）→ 解析回 id，否则玩家/角色对不上自见状态。
    faction:<faction> 用的是阵营值（ally/enemy/neutral）不是名字，无需解析。"""
    if vis and vis.startswith("self:"):
        cid = resolve_id(s, vis.split(":", 1)[1])
        if cid:
            return f"self:{cid}"
    return vis


def _to_cond(s: Session, d: DeltaItem, turn: int) -> Condition:
    return Condition(content=d.content, gates=d.gates, severity=d.severity,
                     visibility=_normalize_vis(s, d.visibility), source="adjudication",
                     ttl=d.ttl, created_turn=turn)


def _remove_matching(conds: List[Condition], key: str) -> List[Condition]:
    return [c for c in conds if key not in c.content]


def apply_delta(s: Session, adj: Adjudication) -> None:
    delta = adj.ledger_delta
    turn = s.turn
    # add
    for d in delta.add:
        cond = _to_cond(s, d, turn)
        if d.subject == "scene":
            if d.category == "spatial":
                s.ledger.scene.spatial.append(cond)
            elif d.category in ("social_facts", "承诺", "协议", "结盟", "停火"):
                s.ledger.scene.social_facts.append(cond)
            else:
                s.ledger.scene.scene_facts.append(cond)
        else:
            bid = resolve_id(s, d.subject)        # 主体可能是名字或 id
            if bid and bid in s.ledger.characters:
                cl = s.ledger.characters[bid]
                if d.category == "posture":
                    cl.posture = d.content
                elif d.category == "status_effects":
                    cl.status_effects.append(cond)
                else:
                    cl.conditions.append(cond)
    # remove（以关键字匹配；跳过空串——否则 "" in content 恒真会清空整列）
    for key in delta.remove:
        if not key:
            continue
        for cl in s.ledger.characters.values():
            cl.conditions = _remove_matching(cl.conditions, key)
            cl.status_effects = _remove_matching(cl.status_effects, key)
        s.ledger.scene.scene_facts = _remove_matching(s.ledger.scene.scene_facts, key)
        s.ledger.scene.spatial = _remove_matching(s.ledger.scene.spatial, key)
        s.ledger.scene.social_facts = _remove_matching(s.ledger.scene.social_facts, key)
    # modify（简化：当作 add 一条新状况）
    for d in delta.modify:
        bid = resolve_id(s, d.subject)
        if bid and bid in s.ledger.characters:
            s.ledger.characters[bid].conditions.append(_to_cond(s, d, turn))
    # 衍生字段更新（键可能是名字或 id，统一 resolve_id）
    for k, sp in adj.speed_updates.items():
        cid = resolve_id(s, k)
        if cid and cid in s.ledger.characters:
            s.ledger.characters[cid].speed = sp
    for k, cap in adj.perception_updates.items():
        cid = resolve_id(s, k)
        if cid and cid in s.ledger.characters:
            s.ledger.characters[cid].perception = cap
    # faction_changes（倒戈/投靠/被策反）：就地改角色卡阵营，影响今后的同阵营可见性
    for k, fac in adj.faction_changes.items():
        cid = resolve_id(s, k)
        if cid and fac:
            s.cards[cid].faction = fac


# ───────────────── 结构化日志条目（actor + 我方输入文本，供前端展示） ─────────────────
def log_system_entry(text: str) -> dict:
    """系统行（scene/开场/ended）：无行动者。"""
    return {"narration": text, "actor": None, "actor_name": None, "faction": None, "controller": None,
            "action_text": None, "reaction_text": None, "reactor_name": None}


def visible_action_text(intent, ally: bool, cover: str = "",
                        detected: bool = False, resolved: bool = True) -> Optional[str]:
    """玩家在「action chip」上看到的该角色明面动作（按隐蔽与否分流）。真值表：

      开放(not covert)，任意阵营/任意时点      → 真意(intent.action)   # 含敌方、含预告帧
      covert + 行动者我方                      → 真意                # 玩家与其同阵营，知底
      covert + 非我方 + 裁决前(预告帧)         → None                # 敌方隐蔽不预告
      covert + 非我方 + 裁决后 + 被识破         → 真意                # 伪装被看穿，真相暴露
      covert + 非我方 + 裁决后 + 未识破         → cover or None        # 蒙混过关显伪装；裁决漏填也绝不漏真意

    注：本闸门「显什么」用表象/真意分流；而 is_contested 等**判定**始终用真意（intent.action），二者有意分开。"""
    if not getattr(intent, "covert", False):
        return intent.action
    if ally:
        return intent.action
    if not resolved:
        return None
    if detected:
        return intent.action
    return cover or None


def log_action_entry(s: Session, intent, reaction, actor: str, narration: str,
                     cover: str = "", detected: bool = False, resolved: bool = True,
                     time_skip: str = "") -> dict:
    """一拍的结构化记录：总记行动者；行动文本按 visible_action_text 分流
    （开放行动连敌方也可见；隐蔽敌方裁决前不显、裁决后显表象/被识破才显真意）。反应文本仍仅我方可见（本轮不动）。
    推进非空＝本拍含时间跳跃，供前端画「时间流逝」分隔线。"""
    card = s.cards.get(actor)
    ally = bool(card and card.faction == "ally")
    e = {
        "narration": narration,
        "actor": actor,
        "actor_name": card.name if card else actor,
        "faction": card.faction if card else "",
        "controller": card.controller if card else "",   # 「player」/「agent」——判定是不是玩家用（不靠 id）
        "action_text": visible_action_text(intent, ally, cover, detected, resolved),
        "reaction_text": None,
        "reactor_name": None,
        "time_skip": time_skip or None,             # 时间跳跃描述（非空才显分隔线）；预告帧/普通拍为 None
    }
    if reaction is not None:
        rc = s.cards.get(reaction.actor)
        if rc and rc.faction == "ally":
            e["reaction_text"] = reaction.reaction
            e["reactor_name"] = rc.name
    return e


def log_pending_entry(s: Session, actor: str, intent, reaction=None) -> dict:
    """进行中的拍（叙事未出，narration=None）：与 log_action_entry 同闸门但 resolved=False
    ——故敌方隐蔽行动在裁决前恒不预告；开放行动（含敌方）与我方行动则照样提前显示。"""
    return log_action_entry(s, intent, reaction, actor, None, resolved=False)


# ───────────────── 分发叙事（GM 写、程序送） ─────────────────
def distribute(s: Session, public: str, private: dict) -> None:
    s.public_log.append(public)
    # 私密叙事的键可能是角色名（agent 用名），解析回 id 再按角色分发
    by_id = {}
    for k, v in (private or {}).items():
        cid = resolve_id(s, k)
        if cid:
            by_id[cid] = v
    for cid in s.scene.present:
        msg = by_id.get(cid) or public
        s.memory.setdefault(cid, []).append(msg)


# ───────────────── 账本清理：瞬态 TTL 自动过期 ─────────────────
def _alive(c: Condition, turn: int) -> bool:
    if c.ttl is None or c.created_turn is None:
        return True
    return (turn - c.created_turn) < c.ttl


def expire_transients(s: Session) -> None:
    """移除已到期的瞬态状态（剩余拍数用尽）。每拍结束调用。"""
    turn = s.turn
    for cl in s.ledger.characters.values():
        cl.conditions = [c for c in cl.conditions if _alive(c, turn)]
        cl.status_effects = [c for c in cl.status_effects if _alive(c, turn)]
    sc = s.ledger.scene
    sc.scene_facts = [c for c in sc.scene_facts if _alive(c, turn)]
    sc.spatial = [c for c in sc.spatial if _alive(c, turn)]
    sc.social_facts = [c for c in sc.social_facts if _alive(c, turn)]


# ───────────────── 结束条件 ─────────────────
def check_end(s: Session) -> Optional[str]:
    for cid, cl in s.ledger.characters.items():
        blob = " ".join(c.content for c in cl.conditions + cl.status_effects)
        if any(k in blob for k in ("死亡", "毙命", "重缚无法脱身", "彻底制伏")):
            return f"{s.cards[cid].name} 已退场：{blob}"
    return None
