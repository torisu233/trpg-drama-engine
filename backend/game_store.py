"""游戏场次管理：在内存持有进行中的 Session，并存盘到 data/games/*.json。

游玩是「有状态」的——每个 game_id 对应一个 Session；每次行动后存盘，重启可续。
（Session 全可串行化：角色记忆只是字符串数组。）
"""
import json
import uuid
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from .models import Session
from . import scenario as scen, engine, config

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


def delete_game(gid: str) -> bool:
    _cache.pop(gid, None)
    path = GAMES_DIR / f"{gid}.json"
    if path.exists():
        path.unlink()
        return True
    return False


def list_games() -> List[dict]:
    if not GAMES_DIR.exists():
        return []
    out = []
    for p in sorted(GAMES_DIR.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            out.append({
                "game_id": p.stem,
                "地点": d.get("scene", {}).get("地点", ""),
                "回合数": d.get("回合数", 0),
                "结束": d.get("结束"),
            })
        except Exception:
            continue
    return out


def _action_bar(s: Session) -> list:
    """各角色行动值与预估还要几拍才行动；最接近行动者排最上面。"""
    th = config.ACTION_THRESHOLD
    bars = []
    for cid in s.scene.在场:
        cl = s.会变层.角色.get(cid)
        if not cl:
            continue
        速 = max(cl.行动速度, 1)
        需 = max(th - cl.行动值, 0)
        bars.append({
            "id": cid, "名": s.角色卡[cid].名, "阵营": s.角色卡[cid].阵营,
            "行动值": cl.行动值, "速度": cl.行动速度, "门槛": th,
            "预估拍": (需 + 速 - 1) // 速,
        })
    bars.sort(key=lambda b: (b["预估拍"], -b["行动值"]))
    return bars


def snapshot(gid: str, s: Session) -> dict:
    return {
        "game_id": gid,
        "回合数": s.回合数,
        "结束": s.结束,
        "pending": s.pending,
        "公开日志": s.公开日志,
        "在场": [{"id": cid, "名": s.角色卡[cid].名, "阵营": s.角色卡[cid].阵营}
                 for cid in s.scene.在场 if cid in s.角色卡],
        "行动条": _action_bar(s),
        "玩家视图": engine.build_view(s, "player"),
        "帐本调试": engine.ground_truth(s),
    }
