"""游戏场次：存在 DB（games.state JSON 列），绑 user_id。

DB 为唯一真相——不再用内存缓存（多 ECS task 才一致）。每请求从 DB 载入 Session、改、存回；
串流时逐拍存回。游戏永远私人：列/读/删仅本人 / admin。
"""
import uuid
from .models import Session
from .models_db import Game, User, Scenario as DBScenario
from . import scenario as scen, config


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _dump(s: Session) -> dict:
    return s.model_dump(mode="json")


def create_game(db, s: Session, user_id: int, scenario_id=None) -> str:
    """把一份（已建好、已校验可玩的）Session 写入 DB，绑 user_id。返回 gid。

    刻意收一份现成 Session（而非 Scenario）：让路由能在持久化**之前**先 validate_playable，
    不完整剧本直接 400、不留孤儿 Game 行。"""
    gid = _new_id()
    db.add(Game(id=gid, user_id=user_id, scenario_id=scenario_id,
                state=_dump(s), turn_count=s.turn, ended=s.ended))
    db.commit()
    return gid


def load_game(db, gid: str):
    """取游戏行（含 user_id，供拥有权检查）；不存在/已删返回 None。"""
    return db.query(Game).filter(Game.id == gid, Game.is_active.is_(True)).first()


def session_of(row: Game) -> Session:
    from . import engine
    s = Session(**row.state)
    engine.prune_orphans(s)   # 读档侧也守一道：已存的不一致状态不致在后续回合让裁决/视图 KeyError
    return s


def save_game(db, gid: str, s: Session) -> None:
    row = db.query(Game).filter(Game.id == gid).first()
    if not row:
        return
    row.state = _dump(s)
    row.turn_count = s.turn
    row.ended = s.ended
    db.commit()


def delete_game(db, gid: str) -> bool:
    row = db.query(Game).filter(Game.id == gid, Game.is_active.is_(True)).first()
    if not row:
        return False
    row.is_active = False     # 软删除
    db.commit()
    return True


def list_games(db, user: User) -> list:
    q = db.query(Game).filter(Game.is_active.is_(True))
    if not user.is_admin:
        q = q.filter(Game.user_id == user.id)
    rows = q.order_by(Game.updated_at.desc()).all()
    owners = {}
    if user.is_admin and rows:
        ids = {r.user_id for r in rows}
        owners = {u.id: u.username for u in db.query(User).filter(User.id.in_(ids))}
    # scenario_name：经 scenario_id 关联 title（含已软删的剧本仍可取名）
    titles = {}
    sids = {r.scenario_id for r in rows if r.scenario_id}
    if sids:
        titles = {s.id: s.title for s in db.query(DBScenario).filter(DBScenario.id.in_(sids))}
    out = []
    for r in rows:
        scene = (r.state or {}).get("scene", {})
        out.append({
            "game_id": r.id,
            "scenario_name": titles.get(r.scenario_id) or scene.get("location", "") or r.id,
            "location": scene.get("location", ""),
            "turn": r.turn_count,
            "ended": r.ended,
            "owner": owners.get(r.user_id) if user.is_admin else None,
        })
    return out


# ───────────────── 快照（纯函数，喂前端）─────────────────
def _action_bar(s: Session) -> list:
    """各角色行动值与预估还要几拍才行动；最接近行动者排最上面。"""
    th = config.ACTION_THRESHOLD
    bars = []
    for cid in s.scene.present:
        cl = s.ledger.characters.get(cid)
        if not cl:
            continue
        速 = max(cl.speed, 1)
        需 = max(th - cl.gauge, 0)
        bars.append({
            "id": cid, "name": s.cards[cid].name, "faction": s.cards[cid].faction,
            "gauge": cl.gauge, "速度": cl.speed, "threshold": th,
            "beats": (需 + 速 - 1) // 速,
        })
    bars.sort(key=lambda b: (b["beats"], -b["gauge"]))
    return bars


def snapshot(gid: str, s: Session) -> dict:
    from . import engine
    return {
        "game_id": gid,
        "turn": s.turn,
        "ended": s.ended,
        "pending": s.pending,
        "in_progress": s.in_progress,
        "public_log": s.public_log,
        "log": s.log,
        "present": [{"id": cid, "name": s.cards[cid].name, "faction": s.cards[cid].faction,
                  "controller": s.cards[cid].controller}
                 for cid in s.scene.present if cid in s.cards],
        "action_bar": _action_bar(s),
        "situation": engine.player_situation(s),
        "characters": engine.known_characters(s),
        "ledger_debug": engine.ground_truth(s),
    }
