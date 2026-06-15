"""内核引擎（纯逻辑，无 API）：行动条、两轴判定、迷雾过滤、delta 套用。

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
    兼容三种输入：已是 id → 原样；是某角色的「名」→ 该 id；都不匹配 → None。"""
    if not key:
        return None
    if key in s.角色卡:                       # 已是 id
        return key
    for cid, c in s.角色卡.items():            # 按名字匹配（名字应唯一）
        if c.名 == key:
            return cid
    return None


# ───────────────── 行动条 ─────────────────
def _tick(s: Session) -> None:
    for cl in s.会变层.角色.values():
        cl.行动值 += cl.行动速度


def pick_actor(s: Session) -> str:
    """每次调用先 +1 拍；没人达门槛就继续加，直到有人达标。返回行动者 id。"""
    _tick(s)  # 「场上每行动一次，大家加一次」
    while not any(cl.行动值 >= config.ACTION_THRESHOLD for cl in s.会变层.角色.values()):
        _tick(s)
    ready = [cid for cid, cl in s.会变层.角色.items()
             if cl.行动值 >= config.ACTION_THRESHOLD]
    if PLAYER in ready:                       # 平手：玩家优先
        return PLAYER
    return max(ready, key=lambda c: s.会变层.角色[c].行动值)  # 否则行动值高者


def consume_turn(s: Session, actor: str) -> None:
    s.会变层.角色[actor].行动值 -= config.ACTION_THRESHOLD   # 扣门槛、保留溢出


def beats_to_act(cl, threshold: int = config.ACTION_THRESHOLD) -> int:
    """还差几拍这个角色才到行动门槛（程序算好；负初始行动值→很多拍后，模拟缓慢逼近）。"""
    速 = max(cl.行动速度, 1)
    需 = max(threshold - cl.行动值, 0)
    return (需 + 速 - 1) // 速


def action_order(s: Session) -> list:
    """在场角色按「还有几拍轮到」升序：[(cid, 名, 阵营, 预估拍)…]。供 agent 了解行动次序与逼近。"""
    rows = []
    for cid in s.scene.在场:
        cl = s.会变层.角色.get(cid)
        if cl is None or cid not in s.角色卡:
            continue
        rows.append((cid, s.角色卡[cid].名, s.角色卡[cid].阵营, beats_to_act(cl)))
    rows.sort(key=lambda t: (t[3], -s.会变层.角色[t[0]].行动值))
    return rows


# ───────────────── 感知 / 两轴 ─────────────────
def _perceives(s: Session, who: str) -> bool:
    cap = s.会变层.角色[who].感知能力
    return not any(k in cap for k in ("昏迷", "失去意识"))


def _can_oppose(s: Session, who: str) -> bool:
    cl = s.会变层.角色[who]
    if any(k in cl.感知能力 for k in ("昏迷", "失去意识")):
        return False
    blob = " ".join(c.内容 for c in cl.特殊情况)
    return not any(k in blob for k in INCAPACITATED_KW)


def target_char(s: Session, intent) -> Optional[str]:
    t = resolve_id(s, intent.目标)            # 目标可能是名字或 id，统一解析回 id
    if t and t in s.会变层.角色 and t != intent.actor:
        return t
    return None


def needs_reaction(s: Session, intent) -> Optional[str]:
    """轴 A：是否该向某角色收反应？返回该角色 id 或 None。
    闸门：对方是角色 ∧（是玩家 ∨（感知得到 ∧ 能对抗））。模棱两可宁可多收。"""
    tgt = target_char(s, intent)
    if not tgt:
        return None
    if tgt == PLAYER:
        return PLAYER                       # 对玩家一定收
    if _perceives(s, tgt) and _can_oppose(s, tgt):
        return tgt
    return None


def is_contested(s: Session, intent, reaction_target: Optional[str]) -> bool:
    """轴 B：是否争议（掷运气）？被主动对抗 或 环境本身是赌注。"""
    if reaction_target:
        return True
    return any(k in (intent.行动 or "") for k in RISKY_KW)


def roll_luck() -> str:
    return random.choices(config.LUCK_TIERS, weights=config.LUCK_WEIGHTS, k=1)[0]


# ───────────────── 迷雾：产出某角色可见的视图文字 ─────────────────
def _visible(cond: Condition, viewer: str, faction: str) -> bool:
    v = cond.可见性
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
        d = f"[{c.程度}]" if c.程度 else ""
        out.append(f"{c.内容}{d}{g}")
    return out


def build_view(s: Session, viewer: str) -> str:
    """组出 viewer 能看到的局面文字（喂给角色 agent）。维持迷雾。"""
    faction = s.角色卡[viewer].阵营
    lines = [f"【场景】{s.scene.地点}"]

    # 场景公开事实
    facts = _fmt_conds(s.会变层.场景.场景事实, viewer, faction) \
        + _fmt_conds(s.会变层.场景.空间关系, viewer, faction)
    if facts:
        lines.append("【场面】" + "；".join(facts))
    social = _fmt_conds(s.会变层.场景.社会事实, viewer, faction)
    if social:
        lines.append("【约定/情报】" + "；".join(social))

    # 各角色（自己看全部；别人只看公开＋可见）
    for cid, cl in s.会变层.角色.items():
        if cid not in s.scene.在场:
            continue
        card = s.角色卡[cid]
        g = f"，{card.性别}" if card.性别 else ""
        self_mark = "·本人" if cid == viewer else ""   # 不用「你」——「你」留给叙事专指主角玩家
        seg = [f"{card.名}（{card.阵营}{g}{self_mark}）：{cl.姿势位置 or '在场'}"]
        body = _fmt_conds(cl.身心状况, viewer, faction) + _fmt_conds(cl.特殊情况, viewer, faction)
        if cid == viewer:                    # 自己能看到自己的随身与物品
            body += _fmt_conds(cl.随身, viewer, faction)
            if cl.物品:
                body.append("持有：" + "、".join(f"{it.名}({it.状态})" for it in cl.物品.values()))
        if body:
            seg.append("，".join(body))
        lines.append(" ".join(seg))

    # 阵营私有计策
    plans = s.会变层.阵营私有.get(faction, {}).get("计策", [])
    if plans:
        lines.append("【我方计策】" + "；".join(plans))

    return "\n".join(lines)


def player_situation(s: Session, viewer: str = PLAYER) -> dict:
    """玩家可见的环境与社会面（迷雾过滤）：场景/场面/约定情报/我方计策。结构化给前端。"""
    fac = s.角色卡[viewer].阵营
    sc = s.会变层.场景
    return {
        "场景": s.scene.地点,
        "场面": _fmt_conds(sc.场景事实, viewer, fac) + _fmt_conds(sc.空间关系, viewer, fac),
        "情报": _fmt_conds(sc.社会事实, viewer, fac),
        "计策": list(s.会变层.阵营私有.get(fac, {}).get("计策", [])),
    }


def known_characters(s: Session, viewer: str = PLAYER) -> list:
    """玩家所知的在场角色（结构化）。
    - 同阵营（含自己）：给完整角色卡——能力/防御/弱点/动机等，对队友本就知情。
    - 敌方：只给可见状态——底细是要靠观察发现的秘密，不注入。
    """
    fac = s.角色卡[viewer].阵营
    out = []
    for cid in s.scene.在场:
        cl = s.会变层.角色.get(cid)
        if cid not in s.角色卡 or cl is None:
            continue
        card = s.角色卡[cid]
        ally = card.阵营 == fac
        item = {
            "id": cid, "名": card.名, "阵营": card.阵营, "性别": card.性别,
            "是自己": cid == viewer, "是我方": ally,
            "姿势位置": cl.姿势位置, "行动速度": cl.行动速度, "感知能力": cl.感知能力,
            "状态": _fmt_conds(cl.身心状况, viewer, fac) + _fmt_conds(cl.特殊情况, viewer, fac),
        }
        if ally:                                  # 我方互知底细
            item.update({
                "身份背景": card.身份背景, "性格": card.性格, "说话风格": card.说话风格,
                "动机目标": card.动机目标, "行为偏好": card.行为偏好,
                "能力": card.能力, "防御特性": card.防御特性, "弱点": card.弱点,
            })
            if cid == viewer and cl.物品:         # 自己看得到随身物品
                item["持有"] = [f"{it.名}（{it.状态}）" for it in cl.物品.values()]
        out.append(item)
    return out


def faction_mates(s: Session, cid: str) -> List[str]:
    """与 cid 同阵营、在场的其他角色 id（同阵营互看整张卡用；跨阵营不含）。"""
    me = s.角色卡.get(cid)
    if not me:
        return []
    return [oid for oid in s.scene.在场
            if oid != cid and oid in s.角色卡 and s.角色卡[oid].阵营 == me.阵营]


def ground_truth(s: Session) -> str:
    """给裁决的完整地面真相（全可见，含 gm 秘密）。"""
    lines = [f"【场景】{s.scene.地点}"]
    for c in s.会变层.场景.场景事实 + s.会变层.场景.空间关系 + s.会变层.场景.社会事实:
        tag = "" if c.可见性 == "public" else f" <{c.可见性}>"
        g = f"（{c.gates}）" if c.gates else ""
        lines.append(f"- {c.内容}{g}{tag}")
    for cid, cl in s.会变层.角色.items():
        card = s.角色卡[cid]
        g = f"/{card.性别}" if card.性别 else ""
        lines.append(f"◆ {card.名}（{card.阵营}{g}）速度{cl.行动速度} 感知:{cl.感知能力}")
        if card.能力:
            lines.append(f"  能力：{'、'.join(card.能力)}")
        if card.防御特性:
            lines.append(f"  防御特性：{'、'.join(card.防御特性)}")
        if card.弱点:
            lines.append(f"  弱点：{'、'.join(card.弱点)}")
        lines.append(f"  姿势位置：{cl.姿势位置}")
        for c in cl.身心状况 + cl.特殊情况 + cl.随身:
            tag = "" if c.可见性 == "public" else f" <{c.可见性}>"
            g = f"（{c.gates}）" if c.gates else ""
            lines.append(f"  - {c.内容}{g}{tag}")
        for it in cl.物品.values():
            lines.append(f"  - 物品 {it.名}：{it.状态}，{it.位置}")
    return "\n".join(lines)


# ───────────────── 套用裁决 delta（防御式，绝不崩） ─────────────────
def _normalize_vis(s: Session, vis: str) -> str:
    """可见性 self:<X> 里 X 可能是名字（agent 用名）→ 解析回 id，否则玩家/角色对不上自见状态。
    faction:<阵营> 用的是阵营值（我方/敌/中立）不是名字，无需解析。"""
    if vis and vis.startswith("self:"):
        cid = resolve_id(s, vis.split(":", 1)[1])
        if cid:
            return f"self:{cid}"
    return vis


def _to_cond(s: Session, d: DeltaItem, turn: int) -> Condition:
    return Condition(内容=d.内容, gates=d.gates, 程度=d.程度,
                     可见性=_normalize_vis(s, d.可见性), 来源="裁决",
                     剩余拍数=d.剩余拍数, 创建回合=turn)


def _remove_matching(conds: List[Condition], key: str) -> List[Condition]:
    return [c for c in conds if key not in c.内容]


def apply_delta(s: Session, adj: Adjudication) -> None:
    delta = adj.ledger_delta
    turn = s.回合数
    # add
    for d in delta.add:
        cond = _to_cond(s, d, turn)
        if d.主体 == "场景":
            if d.类别 == "空间关系":
                s.会变层.场景.空间关系.append(cond)
            elif d.类别 in ("社会事实", "承诺", "协议", "结盟", "停火"):
                s.会变层.场景.社会事实.append(cond)
            else:
                s.会变层.场景.场景事实.append(cond)
        else:
            bid = resolve_id(s, d.主体)        # 主体可能是名字或 id
            if bid and bid in s.会变层.角色:
                cl = s.会变层.角色[bid]
                if d.类别 == "姿势位置":
                    cl.姿势位置 = d.内容
                elif d.类别 == "特殊情况":
                    cl.特殊情况.append(cond)
                else:
                    cl.身心状况.append(cond)
    # remove（以关键字匹配）
    for key in delta.remove:
        for cl in s.会变层.角色.values():
            cl.身心状况 = _remove_matching(cl.身心状况, key)
            cl.特殊情况 = _remove_matching(cl.特殊情况, key)
        s.会变层.场景.场景事实 = _remove_matching(s.会变层.场景.场景事实, key)
        s.会变层.场景.空间关系 = _remove_matching(s.会变层.场景.空间关系, key)
        s.会变层.场景.社会事实 = _remove_matching(s.会变层.场景.社会事实, key)
    # modify（简化：当作 add 一条新状况）
    for d in delta.modify:
        bid = resolve_id(s, d.主体)
        if bid and bid in s.会变层.角色:
            s.会变层.角色[bid].身心状况.append(_to_cond(s, d, turn))
    # 衍生字段更新（键可能是名字或 id，统一 resolve_id）
    for k, sp in adj.速度更新.items():
        cid = resolve_id(s, k)
        if cid and cid in s.会变层.角色:
            s.会变层.角色[cid].行动速度 = sp
    for k, cap in adj.感知更新.items():
        cid = resolve_id(s, k)
        if cid and cid in s.会变层.角色:
            s.会变层.角色[cid].感知能力 = cap
    # 阵营变更（倒戈/投靠/被策反）：就地改角色卡阵营，影响今后的同阵营可见性
    for k, fac in adj.阵营变更.items():
        cid = resolve_id(s, k)
        if cid and fac:
            s.角色卡[cid].阵营 = fac


# ───────────────── 结构化日志条目（行动者 + 我方输入文本，供前端展示） ─────────────────
def log_system_entry(text: str) -> dict:
    """系统行（场景/开场/结束）：无行动者。"""
    return {"叙事": text, "行动者": None, "行动者名": None, "阵营": None, "扮演": None,
            "行动文本": None, "反应文本": None, "反应者名": None}


def log_action_entry(s: Session, intent, reaction, actor: str, narration: str) -> dict:
    """一拍的结构化记录：总记行动者；行动者/反应者属我方时附带其输入文本（敌方意图不泄露）。"""
    card = s.角色卡.get(actor)
    ally = bool(card and card.阵营 == "我方")
    e = {
        "叙事": narration,
        "行动者": actor,
        "行动者名": card.名 if card else actor,
        "阵营": card.阵营 if card else "",
        "扮演": card.扮演 if card else "",   # 「玩家」/「agent」——判定是不是玩家用（不靠 id）
        "行动文本": intent.行动 if ally else None,
        "反应文本": None,
        "反应者名": None,
    }
    if reaction is not None:
        rc = s.角色卡.get(reaction.actor)
        if rc and rc.阵营 == "我方":
            e["反应文本"] = reaction.反应
            e["反应者名"] = rc.名
    return e


def log_pending_entry(s: Session, actor: str, intent, reaction=None) -> dict:
    """进行中的拍（叙事未出）：与 log_action_entry 同样的阵营可见性，但 叙事=None。
    用于延迟遮盖——LLM 每产出一件「玩家可见」的部分（我方行动/我方回应）就先推给前端显示。"""
    e = log_action_entry(s, intent, reaction, actor, None)
    return e


# ───────────────── 分发叙事（GM 写、程序送） ─────────────────
def distribute(s: Session, public: str, private: dict) -> None:
    s.公开日志.append(public)
    # 私密叙事的键可能是角色名（agent 用名），解析回 id 再按角色分发
    by_id = {}
    for k, v in (private or {}).items():
        cid = resolve_id(s, k)
        if cid:
            by_id[cid] = v
    for cid in s.scene.在场:
        msg = by_id.get(cid) or public
        s.记忆.setdefault(cid, []).append(msg)


# ───────────────── 账本清理：瞬态 TTL 自动过期 ─────────────────
def _alive(c: Condition, turn: int) -> bool:
    if c.剩余拍数 is None or c.创建回合 is None:
        return True
    return (turn - c.创建回合) < c.剩余拍数


def expire_transients(s: Session) -> None:
    """移除已到期的瞬态状态（剩余拍数用尽）。每拍结束调用。"""
    turn = s.回合数
    for cl in s.会变层.角色.values():
        cl.身心状况 = [c for c in cl.身心状况 if _alive(c, turn)]
        cl.特殊情况 = [c for c in cl.特殊情况 if _alive(c, turn)]
    sc = s.会变层.场景
    sc.场景事实 = [c for c in sc.场景事实 if _alive(c, turn)]
    sc.空间关系 = [c for c in sc.空间关系 if _alive(c, turn)]
    sc.社会事实 = [c for c in sc.社会事实 if _alive(c, turn)]


# ───────────────── 结束条件 ─────────────────
def check_end(s: Session) -> Optional[str]:
    for cid, cl in s.会变层.角色.items():
        blob = " ".join(c.内容 for c in cl.身心状况 + cl.特殊情况)
        if any(k in blob for k in ("死亡", "毙命", "重缚无法脱身", "彻底制伏")):
            return f"{s.角色卡[cid].名} 已退场：{blob}"
    return None
