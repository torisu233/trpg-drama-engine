"""核心引擎（純邏輯，無 API）：行動條、兩軸判定、迷霧過濾、delta 套用。

這些都是可單測的純函式；agent 呼叫在 agents.py，流程編排在 flow.py。
"""
import random
from typing import List, Optional, Tuple
from .models import Session, Condition, DeltaItem, LedgerDelta, Adjudication
from . import config

PLAYER = "player"

# 觸發「無法反應 / 失能」的關鍵字
INCAPACITATED_KW = ("昏迷", "失去意識", "綁", "縛", "癱", "暈", "制伏", "壓制")
# 環境爭議關鍵字（無對手仍是賭注）
RISKY_KW = ("跳", "攀", "潛", "賭", "搶", "翻越", "撲", "閃身")


# ───────────────── 行動條 ─────────────────
def _tick(s: Session) -> None:
    for cl in s.會變層.角色.values():
        cl.行動值 += cl.行動速度


def pick_actor(s: Session) -> str:
    """每次呼叫先 +1 拍；沒人達門檻就繼續加，直到有人達標。回傳行動者 id。"""
    _tick(s)  # 「場上每行動一次，大家加一次」
    while not any(cl.行動值 >= config.ACTION_THRESHOLD for cl in s.會變層.角色.values()):
        _tick(s)
    ready = [cid for cid, cl in s.會變層.角色.items()
             if cl.行動值 >= config.ACTION_THRESHOLD]
    if PLAYER in ready:                       # 平手：玩家優先
        return PLAYER
    return max(ready, key=lambda c: s.會變層.角色[c].行動值)  # 否則行動值高者


def consume_turn(s: Session, actor: str) -> None:
    s.會變層.角色[actor].行動值 -= config.ACTION_THRESHOLD   # 扣門檻、保留溢出


# ───────────────── 感知 / 兩軸 ─────────────────
def _perceives(s: Session, who: str) -> bool:
    cap = s.會變層.角色[who].感知能力
    return not any(k in cap for k in ("昏迷", "失去意識"))


def _can_oppose(s: Session, who: str) -> bool:
    cl = s.會變層.角色[who]
    if any(k in cl.感知能力 for k in ("昏迷", "失去意識")):
        return False
    blob = " ".join(c.內容 for c in cl.特殊情況)
    return not any(k in blob for k in INCAPACITATED_KW)


def target_char(s: Session, intent) -> Optional[str]:
    t = intent.目標
    if t and t in s.會變層.角色 and t != intent.actor:
        return t
    return None


def needs_reaction(s: Session, intent) -> Optional[str]:
    """軸 A：是否該向某角色收反應？回傳該角色 id 或 None。
    閘門：對方是角色 ∧（是玩家 ∨（感知得到 ∧ 能對抗））。模稜兩可寧可多收。"""
    tgt = target_char(s, intent)
    if not tgt:
        return None
    if tgt == PLAYER:
        return PLAYER                       # 對玩家一定收
    if _perceives(s, tgt) and _can_oppose(s, tgt):
        return tgt
    return None


def is_contested(s: Session, intent, reaction_target: Optional[str]) -> bool:
    """軸 B：是否爭議（擲運氣）？被主動對抗 或 環境本身是賭注。"""
    if reaction_target:
        return True
    blob = (intent.行動 or "") + (intent.方式 or "")
    return any(k in blob for k in RISKY_KW)


def roll_luck() -> str:
    return random.choices(config.LUCK_TIERS, weights=config.LUCK_WEIGHTS, k=1)[0]


# ───────────────── 迷霧：產出某角色可見的視圖文字 ─────────────────
def _visible(cond: Condition, viewer: str, faction: str) -> bool:
    v = cond.可見性
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
        out.append(f"{c.內容}{d}{g}")
    return out


def build_view(s: Session, viewer: str) -> str:
    """組出 viewer 能看到的局面文字（餵給角色 agent）。維持迷霧。"""
    faction = s.角色卡[viewer].陣營
    lines = [f"【場景】{s.scene.地點}"]

    # 場景公開事實
    facts = _fmt_conds(s.會變層.場景.場景事實, viewer, faction) \
        + _fmt_conds(s.會變層.場景.空間關係, viewer, faction)
    if facts:
        lines.append("【場面】" + "；".join(facts))
    social = _fmt_conds(s.會變層.場景.社會事實, viewer, faction)
    if social:
        lines.append("【約定/情報】" + "；".join(social))

    # 各角色（自己看全部；別人只看公開＋可見）
    for cid, cl in s.會變層.角色.items():
        if cid not in s.scene.在場:
            continue
        card = s.角色卡[cid]
        who = "你" if cid == viewer else card.名
        seg = [f"{who}（{card.陣營}）：{cl.姿勢位置 or '在場'}"]
        body = _fmt_conds(cl.身心狀況, viewer, faction) + _fmt_conds(cl.特殊情況, viewer, faction)
        if cid == viewer:                    # 自己能看到自己的隨身與物品
            body += _fmt_conds(cl.隨身, viewer, faction)
            if cl.物品:
                body.append("持有：" + "、".join(f"{it.名}({it.狀態})" for it in cl.物品.values()))
        if body:
            seg.append("，".join(body))
        lines.append(" ".join(seg))

    # 陣營私有計策
    plans = s.會變層.陣營私有.get(faction, {}).get("計策", [])
    if plans:
        lines.append("【我方計策】" + "；".join(plans))

    return "\n".join(lines)


def ground_truth(s: Session) -> str:
    """給裁決的完整地面真相（全可見，含 gm 秘密）。"""
    lines = [f"【場景】{s.scene.地點}"]
    for c in s.會變層.場景.場景事實 + s.會變層.場景.空間關係 + s.會變層.場景.社會事實:
        tag = "" if c.可見性 == "public" else f" <{c.可見性}>"
        g = f"（{c.gates}）" if c.gates else ""
        lines.append(f"- {c.內容}{g}{tag}")
    for cid, cl in s.會變層.角色.items():
        card = s.角色卡[cid]
        lines.append(f"◆ {card.名}[{cid}]（{card.陣營}）速度{cl.行動速度} 感知:{cl.感知能力}")
        if card.能力:
            lines.append(f"  能力：{'、'.join(card.能力)}")
        if card.防禦特性:
            lines.append(f"  防禦特性：{'、'.join(card.防禦特性)}")
        if card.弱點:
            lines.append(f"  弱點：{'、'.join(card.弱點)}")
        lines.append(f"  姿勢位置：{cl.姿勢位置}")
        for c in cl.身心狀況 + cl.特殊情況 + cl.隨身:
            tag = "" if c.可見性 == "public" else f" <{c.可見性}>"
            g = f"（{c.gates}）" if c.gates else ""
            lines.append(f"  - {c.內容}{g}{tag}")
        for it in cl.物品.values():
            lines.append(f"  - 物品 {it.名}：{it.狀態}，{it.位置}")
    return "\n".join(lines)


# ───────────────── 套用裁決 delta（防禦式，絕不崩） ─────────────────
def _to_cond(d: DeltaItem, turn: int) -> Condition:
    return Condition(內容=d.內容, gates=d.gates, 程度=d.程度,
                     可見性=d.可見性, 來源="裁決",
                     剩餘拍數=d.剩餘拍數, 創建回合=turn)


def _remove_matching(conds: List[Condition], key: str) -> List[Condition]:
    return [c for c in conds if key not in c.內容]


def apply_delta(s: Session, adj: Adjudication) -> None:
    delta = adj.ledger_delta
    turn = s.回合數
    # add
    for d in delta.add:
        cond = _to_cond(d, turn)
        if d.主體 == "場景":
            if d.類別 == "空間關係":
                s.會變層.場景.空間關係.append(cond)
            elif d.類別 in ("社會事實", "承諾", "協議", "結盟", "停火"):
                s.會變層.場景.社會事實.append(cond)
            else:
                s.會變層.場景.場景事實.append(cond)
        elif d.主體 in s.會變層.角色:
            cl = s.會變層.角色[d.主體]
            if d.類別 == "姿勢位置":
                cl.姿勢位置 = d.內容
            elif d.類別 == "特殊情況":
                cl.特殊情況.append(cond)
            else:
                cl.身心狀況.append(cond)
    # remove（以關鍵字匹配）
    for key in delta.remove:
        for cl in s.會變層.角色.values():
            cl.身心狀況 = _remove_matching(cl.身心狀況, key)
            cl.特殊情況 = _remove_matching(cl.特殊情況, key)
        s.會變層.場景.場景事實 = _remove_matching(s.會變層.場景.場景事實, key)
        s.會變層.場景.空間關係 = _remove_matching(s.會變層.場景.空間關係, key)
        s.會變層.場景.社會事實 = _remove_matching(s.會變層.場景.社會事實, key)
    # modify（簡化：當作 add 一條新狀況）
    for d in delta.modify:
        if d.主體 in s.會變層.角色:
            s.會變層.角色[d.主體].身心狀況.append(_to_cond(d, turn))
    # 衍生欄位更新
    for cid, sp in adj.速度更新.items():
        if cid in s.會變層.角色:
            s.會變層.角色[cid].行動速度 = sp
    for cid, cap in adj.感知更新.items():
        if cid in s.會變層.角色:
            s.會變層.角色[cid].感知能力 = cap


# ───────────────── 分發敘事（GM 寫、程式送） ─────────────────
def distribute(s: Session, public: str, private: dict) -> None:
    s.公開日誌.append(public)
    for cid in s.scene.在場:
        msg = private.get(cid) or public
        s.記憶.setdefault(cid, []).append(msg)


# ───────────────── 帳本清理：瞬態 TTL 自動過期 ─────────────────
def _alive(c: Condition, turn: int) -> bool:
    if c.剩餘拍數 is None or c.創建回合 is None:
        return True
    return (turn - c.創建回合) < c.剩餘拍數


def expire_transients(s: Session) -> None:
    """移除已到期的瞬態狀態（剩餘拍數用盡）。每拍結束呼叫。"""
    turn = s.回合數
    for cl in s.會變層.角色.values():
        cl.身心狀況 = [c for c in cl.身心狀況 if _alive(c, turn)]
        cl.特殊情況 = [c for c in cl.特殊情況 if _alive(c, turn)]
    sc = s.會變層.場景
    sc.場景事實 = [c for c in sc.場景事實 if _alive(c, turn)]
    sc.空間關係 = [c for c in sc.空間關係 if _alive(c, turn)]
    sc.社會事實 = [c for c in sc.社會事實 if _alive(c, turn)]


# ───────────────── 結束條件 ─────────────────
def check_end(s: Session) -> Optional[str]:
    for cid, cl in s.會變層.角色.items():
        blob = " ".join(c.內容 for c in cl.身心狀況 + cl.特殊情況)
        if any(k in blob for k in ("死亡", "斃命", "重縛無法脫身", "徹底制伏")):
            return f"{s.角色卡[cid].名} 已退場：{blob}"
    return None
