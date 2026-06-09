"""劇本（Scenario）的存取與轉換。

Scenario = 劇本的靜態/初始資料（世界觀+scene+角色卡+初始會變層）。
- list/load/save_scenario：scenarios/*.json 的列出、讀、寫
- scenario_from_session：從一個 Session 抽出 Scenario（用來把手寫場景匯出成種子）
- session_from_scenario：把 Scenario 包成可玩的 Session（初始化執行期欄位）
"""
import json
from pathlib import Path
from typing import List
from .models import Scenario, Session

SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "scenarios"


def list_scenarios() -> List[str]:
    if not SCENARIOS_DIR.exists():
        return []
    return sorted(p.stem for p in SCENARIOS_DIR.glob("*.json"))


def load_scenario(name: str) -> Scenario:
    path = SCENARIOS_DIR / f"{name}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return Scenario(**data)


def save_scenario(scenario: Scenario) -> Path:
    SCENARIOS_DIR.mkdir(exist_ok=True)
    path = SCENARIOS_DIR / f"{scenario.id}.json"
    path.write_text(scenario.model_dump_json(indent=2), encoding="utf-8")
    return path


def scenario_from_session(s: Session, sid: str) -> Scenario:
    """從 Session 抽出靜態/初始資料成 Scenario。"""
    return Scenario(
        id=sid,
        世界觀=s.世界觀.model_copy(deep=True),
        scene=s.scene.model_copy(deep=True),
        角色卡={k: v.model_copy(deep=True) for k, v in s.角色卡.items()},
        會變層=s.會變層.model_copy(deep=True),
    )


def session_from_scenario(sc: Scenario) -> Session:
    """把 Scenario 包成全新可玩 Session（深拷貝靜態資料，初始化執行期欄位）。"""
    記憶 = {cid: [] for cid in sc.scene.在場}
    公開日誌 = []
    if sc.scene.地點:
        公開日誌.append(f"【場景】{sc.scene.地點}")
    if sc.scene.鉤子:
        公開日誌.append(f"【開場】{sc.scene.鉤子}")
    return Session(
        scene=sc.scene.model_copy(deep=True),
        世界觀=sc.世界觀.model_copy(deep=True),
        角色卡={k: v.model_copy(deep=True) for k, v in sc.角色卡.items()},
        會變層=sc.會變層.model_copy(deep=True),
        記憶=記憶,
        公開日誌=公開日誌,
    )
