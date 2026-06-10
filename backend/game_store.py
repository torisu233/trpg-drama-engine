"""遊戲場次管理：在記憶體持有進行中的 Session，並存檔到 data/games/*.json。

遊玩是「有狀態」的——每個 game_id 對應一個 Session；每次行動後存檔，重啟可續。
（Session 全可序列化：角色記憶只是字串陣列。）
"""
import json
import uuid
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from .models import Session
from . import scenario as scen, engine

GAMES_DIR = Path(__file__).resolve().parent.parent / "data" / "games"
_cache: Dict[str, Session] = {}


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def create_game(scenario_id: str) -> Tuple[str, Session]:
    sc = scen.load_scenario(scenario_id)
    s = scen.session_from_scenario(sc)
    gid = _new_id()
    _cache[gid] = s
    save_game(gid, s)
    return gid, s


def get_game(gid: str) -> Optional[Session]:
    if gid in _cache:
        return _cache[gid]
    path = GAMES_DIR / f"{gid}.json"
    if path.exists():
        s = Session(**json.loads(path.read_text(encoding="utf-8")))
        _cache[gid] = s
        return s
    return None


def save_game(gid: str, s: Session) -> None:
    GAMES_DIR.mkdir(parents=True, exist_ok=True)
    (GAMES_DIR / f"{gid}.json").write_text(s.model_dump_json(indent=2), encoding="utf-8")


def list_games() -> List[dict]:
    if not GAMES_DIR.exists():
        return []
    out = []
    for p in sorted(GAMES_DIR.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            out.append({
                "game_id": p.stem,
                "地點": d.get("scene", {}).get("地點", ""),
                "回合數": d.get("回合數", 0),
                "結束": d.get("結束"),
            })
        except Exception:
            continue
    return out


def snapshot(gid: str, s: Session) -> dict:
    return {
        "game_id": gid,
        "回合數": s.回合數,
        "結束": s.結束,
        "pending": s.pending,
        "公開日誌": s.公開日誌,
        "玩家視圖": engine.build_view(s, "player"),
        "帳本除錯": engine.ground_truth(s),
    }
