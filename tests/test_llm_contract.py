"""边界契约测试：用「敌意但合法」的假 LLM 驱动真实的一整拍，守住 LLM↔引擎 的接缝。

为什么需要这层（见此前线上事故）：
其余测试**从不真的呼叫 LLM**（conftest 注释），于是「LLM 吐出的东西和程序假设不一样」这
一整类 bug 在套件里结构性不可见——它们全长在「自由格式 LLM 输出 ↔ 死板程序假设」的边界上：
  · KeyError '凯尔'：LLM 拿**角色名**当感知分发的键，代码却 s.cards[name] 直接索引 → 崩。
  · self:name visibility：LLM 写 self:<name>，代码假设 self:<id> → 自见状态失效。
  · 虚构键：LLM 编出不存在的角色名当键 → 崩。
  · player id≠"player"：靠写死 id 认玩家 → 认错人/卡死。

本文件不调辅助函数，而是把一个 `FakeGrok`（schema 合法、但**键一律用角色名**、含 self:name、
含**虚构键**）接进 `flow`，跑完整的一拍（意图→reaction→adjudication→套用→narration→分发→log），断言：
  (1) 不崩、不卡死；(2) 名字键的 delta/速度/faction/感知/私密叙事都落到了对应角色；
  (3) self:name 归一化成 self:id；(4) 虚构键被静默跳过。
夹具刻意是**非酒馆形状**：player id≠"player"、characters id≠名字，逼出名↔id 的区分。

跑老代码（修复前）时本测试会崩（KeyError）——正是它该有的回归价值。
"""
import asyncio

from backend import flow, engine, config
from backend.models import (
    Session, Scene, CharCard, Ledger, CharLedger,
    Intent, Reaction, Adjudication, LedgerDelta, DeltaItem, Narration,
    Summary, ConsolidateOut,
)


# ───────────────── 敌意假 LLM ─────────────────
class FakeGrok:
    """冒充 GrokClient：按 schema 返回**合法但敌意**的输出（键全用角色名 + self:name + 虚构键）。

    模拟 DeepSeek 的真实倾向：用角色名而非抽象 id 当各种字段的键。绝不联网。
    """
    async def call(self, prompt, schema, temperature=0.7, max_tokens=2000, model=""):
        name = schema.__name__
        if name == "Intent":
            # 敌方黑衣人挥刀逼近队友「阿大」——目标用**角色名**，引擎须在边界解析回 id
            return Intent(action="挥刀逼近阿大，刀光直取其腕", target="阿大", covert=False)
        if name == "Reaction":
            return Reaction(reaction="举起船桨横档当胸一格")
        if name == "Adjudication":
            # 一切以角色为键的字段**全用角色名**，外加一个**虚构键**与 self:name visibility
            return Adjudication(
                feasibility="feasible", outcome="success_with_cost",
                relevant_conditions=["黑衣人快刀", "阿大举桨格挡"],
                rulings=["快刀激活", "格挡改写为受创"],
                ledger_delta=LedgerDelta(add=[
                    DeltaItem(subject="阿大", category="conditions", content="右臂被划伤",
                              gates="使不上重劲", visibility="self:阿大"),   # self:name → 须归一化为 self:id
                ]),
                speed_updates={"阿大": 3},               # 名字键
                perception_updates={"阿大": "吃痛分心"},        # 名字键
                faction_changes={"黑衣人": "neutral"},          # 名字键的倒戈
                perception_map={"林无敌": "all", "查无此人": "none",   # ← 虚构键，老代码在此 KeyError
                          "阿大": "partial", "黑衣人": "all"},
                gm_summary="黑衣人一刀划伤阿大手臂，阿大格挡得险。",
            )
        if name == "Narration":
            return Narration(
                public="渡口湿冷，黑衣人欺身一刀，阿大举桨硬格，火星迸溅，腕上已见血痕。",
                private={"阿大": "阿大只觉右臂一麻，握桨发虚。",   # 名字键
                      "鬼影": "不存在角色的私密视角"},          # ← 虚构键，distribute 须跳过
            )
        if name == "Summary":
            return Summary(summary="（测试摘要）")
        if name == "ConsolidateOut":
            return ConsolidateOut(conditions=[])
        raise AssertionError(f"FakeGrok 未预期的 schema: {name}")

    async def close(self):
        pass


# ───────────────── 非酒馆夹具：player id≠"player"、id≠名字 ─────────────────
def _hostile_session() -> Session:
    """三人局，刻意让形状与酒馆不同，逼出名↔id 的区分。

    行动值精心设置（门槛20/玩家速7/常速5）：首拍只有 h3 达标→敌方先动一整拍；
    其后 h1（player）达标→advance 恰好停在玩家决策点。于是 advance 精确只跑「一拍敌方」。
    """
    cards = {
        "h1": CharCard(name="林无敌", faction="ally", controller="player", gender="男",
                       backstory="落魄剑客", abilities=["剑法精准"], weaknesses=["左肩旧伤"]),
        "h2": CharCard(name="阿大", faction="ally", controller="agent", gender="男",
                       abilities=["力气大"], weaknesses=["头脑简单"]),
        "h3": CharCard(name="黑衣人", faction="enemy", controller="agent", gender="男",
                       abilities=["漕帮快刀"], defenses=["横练护体"], weaknesses=["怕水"]),
    }
    ledger = Ledger(characters={
        "h1": CharLedger(posture="立于船头", speed=config.SPEED_PLAYER, gauge=6),
        "h2": CharLedger(posture="持桨在侧", speed=config.SPEED_NORMAL, gauge=0),
        "h3": CharLedger(posture="踏浪而来", speed=config.SPEED_NORMAL, gauge=15),
    })
    return Session(
        scene=Scene(id="hs", location="夜雾渡口", present=["h1", "h2", "h3"]),
        cards=cards, ledger=ledger,
        memory={"h1": [], "h2": [], "h3": []},
        public_log=["【scene】夜雾渡口"],
    )


def _run(coro):
    return asyncio.run(coro)


# ───────────────── 契约：完整一拍跑通敌意输出 ─────────────────
def test_npc_beat_survives_name_keyed_and_fictional_llm_output():
    """敌方一整拍：意图/reaction/adjudication/叙事全用角色名为键、含 self:name 与虚构键 →
    不崩、不卡死，且所有名字键都落到对应角色，self:name 归一化，虚构键被跳过。"""
    s = _hostile_session()

    # 玩家靠「controller==player」识别，绝不是写死的 "player"
    assert engine.player_id(s) == "h1"

    # 跑到玩家决策点（按行动值设定，恰好只跑一拍敌方）——不抛异常即证明边界全程未崩
    _run(flow.advance(FakeGrok(), s))

    # 停在玩家行动，未卡死
    assert s.pending and s.pending["type"] == "player_action"

    h2 = s.ledger.characters["h2"]
    # 名字键的 ledger_delta（subject="阿大"）落到了 h2
    assert any("右臂被划伤" in c.content for c in h2.conditions), "名字键的 delta 未落到对应角色"
    # self:name → self:id 归一化（修复前会是 self:阿大，自见判定对不上）
    伤 = next(c for c in h2.conditions if "右臂被划伤" in c.content)
    assert 伤.visibility == "self:h2", f"self:name 未归一化为 self:id：{伤.visibility}"
    assert engine._visible(伤, "h2", "ally") is True      # 本人可见
    assert engine._visible(伤, "h1", "ally") is False     # 他人不可见

    # 名字键的 speed_updates / perception_updates 落到 h2
    assert h2.speed == 3, "名字键的 speed_updates 未生效"
    assert "吃痛分心" in h2.perception, "名字键的 perception_updates 未生效"

    # 名字键的 faction_changes（黑衣人→neutral）落到 h3
    assert s.cards["h3"].faction == "neutral", "名字键的 faction_changes 未生效"

    # 私密叙事：名字键 "阿大" 分发到 h2；虚构键 "鬼影" 被跳过、不崩
    assert s.memory["h2"][-1] == "阿大只觉右臂一麻，握桨发虚。", "名字键私密叙事未分发到对应角色"
    assert "右臂一麻" not in s.memory["h1"][-1]               # 玩家拿到公开版，非他人私密
    assert "腕上已见血痕" in s.memory["h1"][-1]               # 公开叙事入玩家记忆


def test_player_beat_survives_name_keyed_llm_output():
    """玩家主动一拍（目标用敌人**名字**）：意图→收反应→adjudication→叙事全程跑通、状态落账，不崩。"""
    s = _hostile_session()
    pid = engine.player_id(s)
    assert pid == "h1"

    # 玩家拔剑刺向「黑衣人」（用名字），引擎在边界 resolve 回 h3 并向其收反应
    action = {"action": "拔剑直刺黑衣人咽喉", "target": "黑衣人", "covert": False}

    async def drive():
        async for _ in flow._player_action_beat(FakeGrok(), s, action):
            pass

    _run(drive())   # 不抛异常即过边界

    # 这一拍已落账：裁决的名字键 delta/速度/faction/private 全部生效（与上同源，复用断言要点）
    h2 = s.ledger.characters["h2"]
    assert any("右臂被划伤" in c.content for c in h2.conditions)
    assert h2.speed == 3
    assert s.cards["h3"].faction == "neutral"
    # 结构化日志记下了这一拍，且玩家行动文本可见（ally）
    last = s.log[-1]
    assert last["actor"] == "h1" and last["controller"] == "player"
    assert last["action_text"] == "拔剑直刺黑衣人咽喉"


class HiddenFakeGrok(FakeGrok):
    """敌方一拍**covert**且蒙混过关：裁决返回 detected=False + cover（伪装明面动作）。"""
    async def call(self, prompt, schema, temperature=0.7, max_tokens=2000, model=""):
        name = schema.__name__
        if name == "Intent":
            # 敌方暗算队友「阿大」（NPC），covert——真意不该进玩家可见层
            return Intent(action="趁人不备摸向阿大背后下毒手", target="阿大", covert=True)
        adj = await super().call(prompt, schema, temperature, max_tokens, model)
        if name == "Adjudication":
            adj.detected = False
            adj.cover = "只是凑近与阿大搭话"
        return adj


def test_hidden_enemy_beat_shows_surface_not_true_intent():
    """敌方隐蔽行动蒙混过关：裁决后的结构化日志 action_text = cover（伪装），真意绝不泄露给玩家。"""
    s = _hostile_session()
    _run(flow.advance(HiddenFakeGrok(), s))   # 跑完敌方那一拍，停在玩家

    foe_beats = [e for e in s.log if e.get("actor") == "h3"]
    assert foe_beats, "敌方隐蔽拍未记入结构化日志"
    last = foe_beats[-1]
    assert last["action_text"] == "只是凑近与阿大搭话"      # 显表象
    assert "下毒手" not in (last["action_text"] or "")        # 真意绝不出现在玩家可见 chip


def test_target_resolves_player_by_role_not_hardcoded_id():
    """敌方意图目标解析：以「controller」认玩家、以名字解析角色，均不依赖写死 id。"""
    s = _hostile_session()
    # 敌方点名玩家（用玩家**名字** "林无敌"）→ 须解析回 h1 并判为「该向玩家收反应」
    intent = Intent(actor="h3", action="回身扑向林无敌", target="林无敌")
    assert engine.target_char(s, intent) == "h1"
    assert engine.needs_reaction(s, intent) == "h1"     # 对玩家一定收反应（靠扮演认出 h1）
