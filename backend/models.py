"""数据模型：world + 两层状态 + 各 agent 的结构化 I/O。

设计依据：跑团交互游戏_设计文档.md
- world（静态）：tone / background / laws（影响裁决的硬规则）
- 第一层 cards（静态）：演戏用字段 + 裁决用特质（对手看不到）
- 第二层 ledger（动态，唯一由裁决 delta 修改）：含「social_facts」
- LLM I/O：意图 / reaction / 裁决双输出 / narration
字段采中文，与设计文档、prompt 对齐。
"""
from __future__ import annotations
from typing import Optional, Dict, List
from pydantic import BaseModel, Field


# ───────────────── world（静态） ─────────────────
class World(BaseModel):
    tone: str = ""                                   # kind/氛围 → GM 语气、角色接地
    background: str = ""                                   # ~200字设置 → 所有 agent 接地
    laws: List[str] = Field(default_factory=list)     # 影响裁决的硬规则 → 裁决必须遵守


# ───────────────── 状态条目 ─────────────────
class Condition(BaseModel):
    content: str
    gates: str = ""                 # 这如何约束后续行动（裁决创建时写）
    severity: Optional[str] = None       # 微醺/醉/烂醉、轻伤/重伤/濒死
    visibility: str = "public"           # public | gm | faction:ally | self:<id>
    source: str = ""
    lifetime: str = ""
    ttl: Optional[int] = None    # None=持久；整数=N 拍后自动过期（瞬态）
    created_turn: Optional[int] = None    # 程序盖章，配合剩余拍数做 TTL


class Item(BaseModel):
    name: str
    kind: str = ""
    traits: List[str] = Field(default_factory=list)   # 稳定
    state: str = "intact"                                  # 可变：intact→缺口→折断
    location: str = ""                                      # 可变：右手→落地


# ───────────────── 第一层：cards（静态） ─────────────────
class CharCard(BaseModel):
    name: str
    faction: str                              # ally / enemy / neutral
    controller: str = "agent"                    # "player" | "agent"
    gender: str = ""                         # 可被对手观察的基本信息（列入视图/名册，防脑补）
    # ── 演戏用（characters agent 与本人读；对手看不到）──
    backstory: str = ""                      # 出身、来历、职业
    directive: str = ""                      # 用户手填的最高优先级人设铁律（保底/调试用）：压过其余人设描述，但不越游戏规则与输出格式；只喂角色 agent，AI 编剧不碰
    personality: List[str] = Field(default_factory=list)
    voice: str = ""                      # 语气/口头禅/用词，让对话有辨识度
    motive: str = ""                      # 他这场想要什么，驱动其选择
    tactics: List[str] = Field(default_factory=list)   # 惯用打法/手段：硬刚/阴招/谈判/拖延/嘲讽…
    # ── 裁决用（裁决全见；对手看不到，可为秘密）──
    abilities: List[str] = Field(default_factory=list)        # 擅长什么（质性）
    defenses: List[str] = Field(default_factory=list)     # 如「横练皮糙肉厚，寻常拳脚难伤」「刀枪不入」
    weaknesses: List[str] = Field(default_factory=list)         # 如「怕火」「左肋旧伤」「贪财可动摇」


# ───────────────── 第二层：ledger（动态） ─────────────────
class CharLedger(BaseModel):
    posture: str = ""
    conditions: List[Condition] = Field(default_factory=list)   # 伤/生理/情绪/对人态度
    status_effects: List[Condition] = Field(default_factory=list)   # 被绑/昏迷/失能
    items: Dict[str, Item] = Field(default_factory=dict)
    carried: List[Condition] = Field(default_factory=list)        # persistent（v1 预留）
    # ── 衍生字段（裁决维护，程序只读）──
    speed: int = 5
    perception: str = "normal"
    gauge: int = 0


class SceneLedger(BaseModel):
    spatial: List[Condition] = Field(default_factory=list)
    scene_facts: List[Condition] = Field(default_factory=list)     # 环境 + 已揭露情报（用可见性控制谁知道）
    social_facts: List[Condition] = Field(default_factory=list)     # 承诺/协议/结盟/停火/招供（带 gates 与可见性）


class Ledger(BaseModel):
    characters: Dict[str, CharLedger] = Field(default_factory=dict)
    scene: SceneLedger = Field(default_factory=SceneLedger)
    faction_private: Dict[str, Dict[str, List[str]]] = Field(default_factory=dict)  # {"ally":{"plans":[...]}}


class Scene(BaseModel):
    id: str
    location: str = ""
    hook: str = ""
    present: List[str] = Field(default_factory=list)


class Session(BaseModel):
    scene: Scene
    world: World = Field(default_factory=World)
    cards: Dict[str, CharCard]
    ledger: Ledger
    memory: Dict[str, List[str]] = Field(default_factory=dict)   # 各角色近期逐字叙事（滚动窗）
    summary: Dict[str, str] = Field(default_factory=dict)          # 各角色「先前剧情」滚动摘要
    public_log: List[str] = Field(default_factory=list)           # 给玩家看的叙事流（纯文本，供记忆/adjudication/向后兼容）
    log: List[dict] = Field(default_factory=list)              # 结构化每拍：{narration,actor,actor_name,faction,action_text(按 visible_action_text 分流),reaction_text(ally)…}
    turn: int = 0
    pending: Optional[dict] = None                            # 等待玩家的状态
    ended: Optional[str] = None                                # 结束原因
    in_progress: Optional[dict] = Field(default=None, exclude=True)  # 临时：当前拍已揭示的可见部分（action/回应，叙事未出）；exclude=True 硬保证不入库


class Scenario(BaseModel):
    """剧本＝Session 的静态/初始部分（去掉运行期字段）。可串行化存 JSON。
    字段给默认值，让编剧过程中的「半成品」也能验证通过。"""
    id: str = "scenario"
    world: World = Field(default_factory=World)
    scene: Scene = Field(default_factory=lambda: Scene(id="scene"))
    cards: Dict[str, CharCard] = Field(default_factory=dict)
    ledger: Ledger = Field(default_factory=Ledger)


# ───────────────── LLM I/O ─────────────────
class Intent(BaseModel):
    """characters／玩家的行动意图（只说想做什么，不声明成败）。"""
    actor: str = ""
    action: str                          # 一句话：想做什么（含具体做法）
    target: Optional[str] = None         # char_id 或 None
    covert: bool = False                 # 想瞒过敌人（cover/真意由裁决拆）
    faction_switch: Optional[str] = None      # 提议自己倒戈/投靠到哪个阵营（ally/enemy/neutral）；由裁决裁定是否生效


class Reaction(BaseModel):
    """被锁定者的回应意图（是意图不是判决；可防御/反击/还嘴/喝止…）。"""
    actor: str = ""
    reaction: str                          # 一句话：你要如何回应（含具体做法）


class DeltaItem(BaseModel):
    subject: str                          # char_id 或 "scene"
    category: str                          # posture/conditions/status_effects/item_state/spatial/scene_facts/social_facts/intel
    content: str
    gates: str = ""
    severity: Optional[str] = None
    visibility: str = "public"
    ttl: Optional[int] = None      # 瞬态给 1-3；持久状态留 null


class LedgerDelta(BaseModel):
    add: List[DeltaItem] = Field(default_factory=list)
    remove: List[str] = Field(default_factory=list)    # 以内容关键字匹配移除
    modify: List[DeltaItem] = Field(default_factory=list)


class Adjudication(BaseModel):
    """裁决双输出：行为裁决 + 知识裁决。"""
    # A. 行为裁决
    relevant_conditions: List[str] = Field(default_factory=list)
    rulings: List[str] = Field(default_factory=list)
    feasibility: str = "feasible"               # impossible/hindered/feasible/needs_rewrite
    outcome: str = "success_with_cost"       # success/success_with_cost/reversal
    ledger_delta: LedgerDelta = Field(default_factory=LedgerDelta)
    speed_updates: Dict[str, int] = Field(default_factory=dict)
    perception_updates: Dict[str, str] = Field(default_factory=dict)
    faction_changes: Dict[str, str] = Field(default_factory=dict)   # char_id → 新阵营；裁决批准的倒戈/投靠/被策反
    # B. 知识裁决
    perception_map: Dict[str, str] = Field(default_factory=dict)  # char_id -> all/partial:.../none
    # 隐蔽行动的表象拆分（仅当本拍行动 covert=True 时有意义）
    detected: bool = False                # 隐蔽是否被识破（看穿真意）；True=暴露，False=蒙混过关
    cover: str = ""                    # 隐蔽且「未被识破」时，旁观者看到的伪装明面动作；被识破/非隐蔽时留空
    # C. time_skip（非战斗推进：时间跳跃）——低对抗场景的反僵持杠杆
    time_skip: str = ""                    # 非空=本拍触发「时间跳跃」，内容是时间压缩描述（如"半个时辰后克洛伊拎着冰淇淋回来了"）；空=不跳。叙事据此压缩跳过死时间，角色不离场
    # D. 给 GM
    gm_summary: str = ""


class Narration(BaseModel):
    public: str
    private: Dict[str, str] = Field(default_factory=dict)     # char_id -> 私密叙事


class Summary(BaseModel):
    summary: str


class CleanCond(BaseModel):
    content: str
    gates: str = ""
    visibility: str = "public"


class ConsolidateOut(BaseModel):
    conditions: List[CleanCond] = Field(default_factory=list)


class AuthorReply(BaseModel):
    """编剧 agent 每回合输出：一句回复 + 至多一个「区块更新」。"""
    reply: str                                # 给用户的话（提问/说明改了什么）
    block: str = "none"                         # world / scene / char / ledger / none(纯提问)
    char_id: Optional[str] = None             # 当 block=char 时，指明哪个角色
    world: Optional[World] = None
    scene: Optional[Scene] = None
    char: Optional[CharCard] = None
    ledger: Optional[Ledger] = None
    missing: List[str] = Field(default_factory=list)   # 还缺/待决
    done: bool = False                        # 是否已足够完整可存盘
