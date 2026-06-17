"""数据模型：世界观 + 两层状态 + 各 agent 的结构化 I/O。

设计依据：跑团交互游戏_设计文档.md
- 世界观（静态）：基调 / 背景 / 法则（影响裁决的硬规则）
- 第一层 角色卡（静态）：演戏用字段 + 裁决用特质（对手看不到）
- 第二层 会变层（动态，唯一由裁决 delta 修改）：含「社会事实」
- LLM I/O：意图 / 反应 / 裁决双输出 / 叙事
字段采中文，与设计文档、prompt 对齐。
"""
from __future__ import annotations
from typing import Optional, Dict, List
from pydantic import BaseModel, Field


# ───────────────── 世界观（静态） ─────────────────
class World(BaseModel):
    基调: str = ""                                   # 类型/氛围 → GM 语气、角色接地
    背景: str = ""                                   # ~200字设置 → 所有 agent 接地
    法则: List[str] = Field(default_factory=list)     # 影响裁决的硬规则 → 裁决必须遵守


# ───────────────── 状态条目 ─────────────────
class Condition(BaseModel):
    内容: str
    gates: str = ""                 # 这如何约束后续行动（裁决创建时写）
    程度: Optional[str] = None       # 微醺/醉/烂醉、轻伤/重伤/濒死
    可见性: str = "public"           # public | gm | faction:我方 | self:<id>
    来源: str = ""
    生命周期: str = ""
    剩余拍数: Optional[int] = None    # None=持久；整数=N 拍后自动过期（瞬态）
    创建回合: Optional[int] = None    # 程序盖章，配合剩余拍数做 TTL


class Item(BaseModel):
    名: str
    类型: str = ""
    固有性质: List[str] = Field(default_factory=list)   # 稳定
    状态: str = "完好"                                  # 可变：完好→缺口→折断
    位置: str = ""                                      # 可变：右手→落地


# ───────────────── 第一层：角色卡（静态） ─────────────────
class CharCard(BaseModel):
    名: str
    阵营: str                              # 我方 / 敌 / 中立
    扮演: str = "agent"                    # "玩家" | "agent"
    性别: str = ""                         # 可被对手观察的基本信息（列入视图/名册，防脑补）
    # ── 演戏用（角色 agent 与本人读；对手看不到）──
    身份背景: str = ""                      # 出身、来历、职业
    扮演铁律: str = ""                      # 用户手填的最高优先级人设铁律（保底/调试用）：压过其余人设描述，但不越游戏规则与输出格式；只喂角色 agent，AI 编剧不碰
    性格: List[str] = Field(default_factory=list)
    说话风格: str = ""                      # 语气/口头禅/用词，让对话有辨识度
    动机目标: str = ""                      # 他这场想要什么，驱动其选择
    行为偏好: List[str] = Field(default_factory=list)   # 惯用打法/手段：硬刚/阴招/谈判/拖延/嘲讽…
    # ── 裁决用（裁决全见；对手看不到，可为秘密）──
    能力: List[str] = Field(default_factory=list)        # 擅长什么（质性）
    防御特性: List[str] = Field(default_factory=list)     # 如「横练皮糙肉厚，寻常拳脚难伤」「刀枪不入」
    弱点: List[str] = Field(default_factory=list)         # 如「怕火」「左肋旧伤」「贪财可动摇」


# ───────────────── 第二层：会变层（动态） ─────────────────
class CharLedger(BaseModel):
    姿势位置: str = ""
    身心状况: List[Condition] = Field(default_factory=list)   # 伤/生理/情绪/对人态度
    特殊情况: List[Condition] = Field(default_factory=list)   # 被绑/昏迷/失能
    物品: Dict[str, Item] = Field(default_factory=dict)
    随身: List[Condition] = Field(default_factory=list)        # persistent（v1 预留）
    # ── 衍生字段（裁决维护，程序只读）──
    行动速度: int = 5
    感知能力: str = "正常"
    行动值: int = 0


class SceneLedger(BaseModel):
    空间关系: List[Condition] = Field(default_factory=list)
    场景事实: List[Condition] = Field(default_factory=list)     # 环境 + 已揭露情报（用可见性控制谁知道）
    社会事实: List[Condition] = Field(default_factory=list)     # 承诺/协议/结盟/停火/招供（带 gates 与可见性）


class Ledger(BaseModel):
    角色: Dict[str, CharLedger] = Field(default_factory=dict)
    场景: SceneLedger = Field(default_factory=SceneLedger)
    阵营私有: Dict[str, Dict[str, List[str]]] = Field(default_factory=dict)  # {"我方":{"计策":[...]}}


class Scene(BaseModel):
    id: str
    地点: str = ""
    钩子: str = ""
    在场: List[str] = Field(default_factory=list)


class Session(BaseModel):
    scene: Scene
    世界观: World = Field(default_factory=World)
    角色卡: Dict[str, CharCard]
    会变层: Ledger
    记忆: Dict[str, List[str]] = Field(default_factory=dict)   # 各角色近期逐字叙事（滚动窗）
    摘要: Dict[str, str] = Field(default_factory=dict)          # 各角色「先前剧情」滚动摘要
    公开日志: List[str] = Field(default_factory=list)           # 给玩家看的叙事流（纯文本，供记忆/裁决/向后兼容）
    日志: List[dict] = Field(default_factory=list)              # 结构化每拍：{叙事,行动者,行动者名,阵营,行动文本(按 visible_action_text 分流),反应文本(我方)…}
    回合数: int = 0
    pending: Optional[dict] = None                            # 等待玩家的状态
    结束: Optional[str] = None                                # 结束原因
    进行中: Optional[dict] = Field(default=None, exclude=True)  # 临时：当前拍已揭示的可见部分（行动/回应，叙事未出）；exclude=True 硬保证不入库


class Scenario(BaseModel):
    """剧本＝Session 的静态/初始部分（去掉运行期字段）。可串行化存 JSON。
    字段给默认值，让编剧过程中的「半成品」也能验证通过。"""
    id: str = "scenario"
    世界观: World = Field(default_factory=World)
    scene: Scene = Field(default_factory=lambda: Scene(id="scene"))
    角色卡: Dict[str, CharCard] = Field(default_factory=dict)
    会变层: Ledger = Field(default_factory=Ledger)


# ───────────────── LLM I/O ─────────────────
class Intent(BaseModel):
    """角色／玩家的行动意图（只说想做什么，不声明成败）。"""
    actor: str = ""
    行动: str                          # 一句话：想做什么（含具体做法）
    目标: Optional[str] = None         # char_id 或 None
    隐蔽: bool = False                 # 想瞒过敌人（表象/真意由裁决拆）
    阵营切换: Optional[str] = None      # 提议自己倒戈/投靠到哪个阵营（我方/敌/中立）；由裁决裁定是否生效


class Reaction(BaseModel):
    """被锁定者的回应意图（是意图不是判决；可防御/反击/还嘴/喝止…）。"""
    actor: str = ""
    反应: str                          # 一句话：你要如何回应（含具体做法）


class DeltaItem(BaseModel):
    主体: str                          # char_id 或 "场景"
    类别: str                          # 姿势位置/身心状况/特殊情况/物品状态/空间关系/场景事实/社会事实/情报
    内容: str
    gates: str = ""
    程度: Optional[str] = None
    可见性: str = "public"
    剩余拍数: Optional[int] = None      # 瞬态给 1-3；持久状态留 null


class LedgerDelta(BaseModel):
    add: List[DeltaItem] = Field(default_factory=list)
    remove: List[str] = Field(default_factory=list)    # 以内容关键字匹配移除
    modify: List[DeltaItem] = Field(default_factory=list)


class Adjudication(BaseModel):
    """裁决双输出：行为裁决 + 知识裁决。"""
    # A. 行为裁决
    相关状态: List[str] = Field(default_factory=list)
    逐条判定: List[str] = Field(default_factory=list)
    可行性: str = "可行"               # 不可能/受阻/可行/需改写
    结果阶梯: str = "成功但有代价"       # 成功/成功但有代价/局势逆转
    ledger_delta: LedgerDelta = Field(default_factory=LedgerDelta)
    速度更新: Dict[str, int] = Field(default_factory=dict)
    感知更新: Dict[str, str] = Field(default_factory=dict)
    阵营变更: Dict[str, str] = Field(default_factory=dict)   # char_id → 新阵营；裁决批准的倒戈/投靠/被策反
    # B. 知识裁决
    感知分发: Dict[str, str] = Field(default_factory=dict)  # char_id -> 全部/部分:.../无
    # 隐蔽行动的表象拆分（仅当本拍行动 隐蔽=True 时有意义）
    识破: bool = False                # 隐蔽是否被识破（看穿真意）；True=暴露，False=蒙混过关
    表象: str = ""                    # 隐蔽且「未被识破」时，旁观者看到的伪装明面动作；被识破/非隐蔽时留空
    # C. 推进（非战斗推进：时间跳跃）——低对抗场景的反僵持杠杆
    推进: str = ""                    # 非空=本拍触发「时间跳跃」，内容是时间压缩描述（如"半个时辰后克洛伊拎着冰淇淋回来了"）；空=不跳。叙事据此压缩跳过死时间，角色不离场
    # D. 给 GM
    GM摘要: str = ""


class Narration(BaseModel):
    公开: str
    私密: Dict[str, str] = Field(default_factory=dict)     # char_id -> 私密叙事


class Summary(BaseModel):
    摘要: str


class CleanCond(BaseModel):
    内容: str
    gates: str = ""
    可见性: str = "public"


class ConsolidateOut(BaseModel):
    conditions: List[CleanCond] = Field(default_factory=list)


class AuthorReply(BaseModel):
    """编剧 agent 每回合输出：一句回复 + 至多一个「区块更新」。"""
    reply: str                                # 给用户的话（提问/说明改了什么）
    区块: str = "none"                         # world / scene / char / ledger / none(纯提问)
    char_id: Optional[str] = None             # 当 区块=char 时，指明哪个角色
    world: Optional[World] = None
    scene: Optional[Scene] = None
    char: Optional[CharCard] = None
    ledger: Optional[Ledger] = None
    missing: List[str] = Field(default_factory=list)   # 还缺/待决
    done: bool = False                        # 是否已足够完整可存盘
