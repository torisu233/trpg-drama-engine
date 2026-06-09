"""資料模型：世界觀 + 兩層狀態 + 各 agent 的結構化 I/O。

設計依據：跑團互動遊戲_設計文件.md
- 世界觀（靜態）：基調 / 背景 / 法則（影響裁決的硬規則）
- 第一層 角色卡（靜態）：演戲用欄位 + 裁決用特質（對手看不到）
- 第二層 會變層（動態，唯一由裁決 delta 修改）：含「社會事實」
- LLM I/O：意圖 / 反應 / 裁決雙輸出 / 敘事
欄位採中文，與設計文件、prompt 對齊。
"""
from __future__ import annotations
from typing import Optional, Dict, List
from pydantic import BaseModel, Field


# ───────────────── 世界觀（靜態） ─────────────────
class World(BaseModel):
    基調: str = ""                                   # 類型/氛圍 → GM 語氣、角色接地
    背景: str = ""                                   # ~200字設定 → 所有 agent 接地
    法則: List[str] = Field(default_factory=list)     # 影響裁決的硬規則 → 裁決必須遵守


# ───────────────── 狀態條目 ─────────────────
class Condition(BaseModel):
    內容: str
    gates: str = ""                 # 這如何約束後續行動（裁決創建時寫）
    程度: Optional[str] = None       # 微醺/醉/爛醉、輕傷/重傷/瀕死
    可見性: str = "public"           # public | gm | faction:我方 | self:<id>
    來源: str = ""
    生命週期: str = ""
    剩餘拍數: Optional[int] = None    # None=持久；整數=N 拍後自動過期（瞬態）
    創建回合: Optional[int] = None    # 程式蓋章，配合剩餘拍數做 TTL


class Item(BaseModel):
    名: str
    類型: str = ""
    固有性質: List[str] = Field(default_factory=list)   # 穩定
    狀態: str = "完好"                                  # 可變：完好→缺口→折斷
    位置: str = ""                                      # 可變：右手→落地


# ───────────────── 第一層：角色卡（靜態） ─────────────────
class CharCard(BaseModel):
    名: str
    陣營: str                              # 我方 / 敵 / 中立
    扮演: str = "agent"                    # "玩家" | "agent"
    性別: str = ""                         # 可被對手觀察的基本資訊（列入視圖/名冊，防腦補）
    # ── 演戲用（角色 agent 與本人讀；對手看不到）──
    身分背景: str = ""                      # 出身、來歷、職業
    性格: List[str] = Field(default_factory=list)
    說話風格: str = ""                      # 語氣/口頭禪/用詞，讓對話有辨識度
    動機目標: str = ""                      # 他這場想要什麼，驅動其選擇
    行為偏好: List[str] = Field(default_factory=list)   # 慣用打法/手段：硬剛/陰招/談判/拖延/嘲諷…
    # ── 裁決用（裁決全見；對手看不到，可為秘密）──
    能力: List[str] = Field(default_factory=list)        # 擅長什麼（質性）
    防禦特性: List[str] = Field(default_factory=list)     # 如「橫練皮糙肉厚，尋常拳腳難傷」「刀槍不入」
    弱點: List[str] = Field(default_factory=list)         # 如「怕火」「左肋舊傷」「貪財可動搖」


# ───────────────── 第二層：會變層（動態） ─────────────────
class CharLedger(BaseModel):
    姿勢位置: str = ""
    身心狀況: List[Condition] = Field(default_factory=list)   # 傷/生理/情緒/對人態度
    特殊情況: List[Condition] = Field(default_factory=list)   # 被綁/昏迷/失能
    物品: Dict[str, Item] = Field(default_factory=dict)
    隨身: List[Condition] = Field(default_factory=list)        # persistent（v1 預留）
    # ── 衍生欄位（裁決維護，程式只讀）──
    行動速度: int = 5
    感知能力: str = "正常"
    行動值: int = 0


class SceneLedger(BaseModel):
    空間關係: List[Condition] = Field(default_factory=list)
    場景事實: List[Condition] = Field(default_factory=list)     # 環境 + 已揭露情報（用可見性控制誰知道）
    社會事實: List[Condition] = Field(default_factory=list)     # 承諾/協議/結盟/停火/招供（帶 gates 與可見性）


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
    世界觀: World = Field(default_factory=World)
    角色卡: Dict[str, CharCard]
    會變層: Ledger
    記憶: Dict[str, List[str]] = Field(default_factory=dict)   # 各角色近期逐字敘事（滾動窗）
    摘要: Dict[str, str] = Field(default_factory=dict)          # 各角色「先前劇情」滾動摘要
    公開日誌: List[str] = Field(default_factory=list)           # 給玩家看的敘事流
    回合數: int = 0
    pending: Optional[dict] = None                            # 等待玩家的狀態
    結束: Optional[str] = None                                # 結束原因


class Scenario(BaseModel):
    """劇本＝Session 的靜態/初始部分（去掉執行期欄位）。可序列化存 JSON。
    欄位給預設值，讓編劇過程中的「半成品」也能驗證通過。"""
    id: str = "scenario"
    世界觀: World = Field(default_factory=World)
    scene: Scene = Field(default_factory=lambda: Scene(id="scene"))
    角色卡: Dict[str, CharCard] = Field(default_factory=dict)
    會變層: Ledger = Field(default_factory=Ledger)


# ───────────────── LLM I/O ─────────────────
class Intent(BaseModel):
    """角色／玩家的行動意圖（只說想做什麼，不宣告成敗）。"""
    actor: str = ""
    行動: str                          # 一句話：想做什麼（含具體做法）
    目標: Optional[str] = None         # char_id 或 None
    隱蔽: bool = False                 # 想瞞過敵人（表象/真意由裁決拆）


class Reaction(BaseModel):
    """被鎖定者的回應意圖（是意圖不是判決；可防禦/反擊/還嘴/喝止…）。"""
    actor: str = ""
    反應: str                          # 一句話：你要如何回應（含具體做法）


class DeltaItem(BaseModel):
    主體: str                          # char_id 或 "場景"
    類別: str                          # 姿勢位置/身心狀況/特殊情況/物品狀態/空間關係/場景事實/社會事實/情報
    內容: str
    gates: str = ""
    程度: Optional[str] = None
    可見性: str = "public"
    剩餘拍數: Optional[int] = None      # 瞬態給 1-3；持久狀態留 null


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


class Summary(BaseModel):
    摘要: str


class CleanCond(BaseModel):
    內容: str
    gates: str = ""
    可見性: str = "public"


class ConsolidateOut(BaseModel):
    conditions: List[CleanCond] = Field(default_factory=list)
