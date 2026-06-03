"""資料模型：兩層狀態 + 各 agent 的結構化 I/O。

設計依據：跑團互動遊戲_設計文件.md
- 第一層 角色卡（靜態）
- 第二層 會變層（動態，唯一由裁決 delta 修改）
- LLM I/O：意圖 / 反應 / 裁決雙輸出 / 敘事
欄位採中文，與設計文件、prompt 對齊。
"""
from __future__ import annotations
from typing import Optional, Dict, List
from pydantic import BaseModel, Field

VISIBILITY = ("public", "gm")  # 或 "faction:<陣營>" / "self:<char_id>"


# ───────────────── 狀態條目 ─────────────────
class Condition(BaseModel):
    內容: str
    gates: str = ""                 # 這如何約束後續行動（裁決創建時寫）
    程度: Optional[str] = None       # 微醺/醉/爛醉、輕傷/重傷/瀕死
    可見性: str = "public"           # public | gm | faction:我方 | self:<id>
    來源: str = ""
    生命週期: str = ""


class Item(BaseModel):
    名: str
    類型: str = ""
    固有性質: List[str] = Field(default_factory=list)   # 穩定
    狀態: str = "完好"                                  # 可變：完好→缺口→折斷
    位置: str = ""                                      # 可變：右手→落地


# ───────────────── 第一層：角色卡（靜態） ─────────────────
class CharCard(BaseModel):
    名: str
    陣營: str                         # 我方 / 敵
    扮演: str = "agent"               # "玩家" | "agent"
    背景: str = ""
    性格: List[str] = Field(default_factory=list)
    能力: List[str] = Field(default_factory=list)


# ───────────────── 第二層：會變層（動態） ─────────────────
class CharLedger(BaseModel):
    姿勢位置: str = ""
    身心狀況: List[Condition] = Field(default_factory=list)
    特殊情況: List[Condition] = Field(default_factory=list)   # 被綁/昏迷/失能
    物品: Dict[str, Item] = Field(default_factory=dict)
    隨身: List[Condition] = Field(default_factory=list)        # persistent（v1 預留）
    # ── 衍生欄位（裁決維護，程式只讀）──
    行動速度: int = 5
    感知能力: str = "正常"
    行動值: int = 0


class SceneLedger(BaseModel):
    空間關係: List[Condition] = Field(default_factory=list)
    場景事實: List[Condition] = Field(default_factory=list)


class Ledger(BaseModel):
    角色: Dict[str, CharLedger] = Field(default_factory=dict)
    場景: SceneLedger = Field(default_factory=SceneLedger)
    陣營私有: Dict[str, Dict[str, List[str]]] = Field(default_factory=dict)  # {"我方":{"計策":[...]}}


class Scene(BaseModel):
    id: str
    地點: str = ""
    鉤子: str = ""
    在場: List[str] = Field(default_factory=list)


class Session(BaseModel):
    scene: Scene
    角色卡: Dict[str, CharCard]
    會變層: Ledger
    記憶: Dict[str, List[str]] = Field(default_factory=dict)   # 各角色持久對話記憶
    公開日誌: List[str] = Field(default_factory=list)           # 給玩家看的敘事流
    回合數: int = 0
    pending: Optional[dict] = None                            # 等待玩家的狀態
    結束: Optional[str] = None                                # 結束原因


# ───────────────── LLM I/O ─────────────────
class Intent(BaseModel):
    """角色／玩家的行動意圖（只說想做什麼，不宣告成敗）。"""
    actor: str = ""
    行動: str                          # 攻擊/說服/後撤/移動/對話/...
    目標: Optional[str] = None         # char_id 或 None
    方式: str = ""
    隱蔽: bool = False                 # 想隱蔽（表象/真意由裁決拆）


class Reaction(BaseModel):
    """防禦者的反應意圖（是意圖不是判決）。"""
    actor: str = ""
    類型: str                          # 閃避/格擋/反擊/抗拒/假意順從/硬抗/...
    方式: str = ""


class DeltaItem(BaseModel):
    主體: str                          # char_id 或 "場景"
    類別: str                          # 姿勢位置/身心狀況/特殊情況/物品狀態/空間關係/場景事實
    內容: str
    gates: str = ""
    程度: Optional[str] = None
    可見性: str = "public"


class LedgerDelta(BaseModel):
    add: List[DeltaItem] = Field(default_factory=list)
    remove: List[str] = Field(default_factory=list)    # 以內容關鍵字匹配移除
    modify: List[DeltaItem] = Field(default_factory=list)


class Adjudication(BaseModel):
    """裁決雙輸出：行為裁決 + 知識裁決。"""
    # A. 行為裁決
    相關狀態: List[str] = Field(default_factory=list)
    逐條判定: List[str] = Field(default_factory=list)
    可行性: str = "可行"               # 不可能/受阻/可行/需改寫
    結果階梯: str = "成功但有代價"       # 成功/成功但有代價/局勢逆轉
    ledger_delta: LedgerDelta = Field(default_factory=LedgerDelta)
    速度更新: Dict[str, int] = Field(default_factory=dict)
    感知更新: Dict[str, str] = Field(default_factory=dict)
    # B. 知識裁決
    感知分發: Dict[str, str] = Field(default_factory=dict)  # char_id -> 全部/部分:.../無
    # C. 給 GM
    GM摘要: str = ""


class Narration(BaseModel):
    公開: str
    私密: Dict[str, str] = Field(default_factory=dict)     # char_id -> 私密敘事
