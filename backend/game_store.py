"""Game sessions: stored in the DB (games.state JSON column), bound to user_id.

The DB is the single source of truth — no in-memory cache (so multiple instances stay consistent). Each request loads the
Session from the DB, modifies it, and saves it back; streaming saves after every beat. Games are always private: list/read/delete by owner / admin only.
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
    """Write a (built and validated-as-playable) Session to the DB, bound to user_id. Returns the gid.

    Deliberately takes a ready Session (not a Scenario) so the route can run validate_playable **before** persisting:
    an incomplete scenario gets a 400 straight away and leaves no orphan Game row."""
    gid = _new_id()
    db.add(Game(id=gid, user_id=user_id, scenario_id=scenario_id,
                state=_dump(s), turn_count=s.turn, ended=s.ended))
    db.commit()
    return gid


def load_game(db, gid: str):
    """Fetch the game row (incl. user_id, for ownership checks); None if missing/deleted."""
    return db.query(Game).filter(Game.id == gid, Game.is_active.is_(True)).first()


def session_of(row: Game) -> Session:
    from . import engine
    s = Session(**row.state)
    engine.prune_orphans(s)   # guard on load too: inconsistent saved state must not KeyError in adjudication/views on later turns
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
    row.is_active = False     # soft delete
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
    # scenario_name: title joined via scenario_id (soft-deleted scenarios still provide a name)
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


# ───────────────── snapshot (pure function, feeds the frontend) ─────────────────
def _action_bar(s: Session) -> list:
    """Each character's gauge and estimated beats until acting; the closest to acting comes first."""
    th = config.ACTION_THRESHOLD
    bars = []
    for cid in s.scene.present:
        cl = s.ledger.characters.get(cid)
        if not cl:
            continue
        spd = max(cl.speed, 1)
        need = max(th - cl.gauge, 0)
        bars.append({
            "id": cid, "name": s.cards[cid].name, "faction": s.cards[cid].faction,
            "gauge": cl.gauge, "speed": cl.speed, "threshold": th,
            "beats": (need + spd - 1) // spd,
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
