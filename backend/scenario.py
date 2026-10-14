"""Scenario conversions.

All storage lives in the DB (see models_db.Scenario); this module only handles Pydantic conversions:
scenario_from_session / session_from_scenario / apply_author_reply (author merge).
DB initialization no longer injects any demo scenario — scenarios are always created by users via the author page/API and stored in the DB.
"""
from .models import Scenario, Session, CharLedger
from . import engine, config


def scenario_from_session(s: Session, sid: str) -> Scenario:
    """Extract the static/initial data of a Session into a Scenario."""
    return Scenario(
        id=sid,
        world=s.world.model_copy(deep=True),
        scene=s.scene.model_copy(deep=True),
        cards={k: v.model_copy(deep=True) for k, v in s.cards.items()},
        ledger=s.ledger.model_copy(deep=True),
    )


def _nonempty(v) -> bool:
    return v not in (None, "", [], {})


def _merge_fields(existing, new, fields) -> None:
    """Field-by-field merge: an empty field from the agent means "unchanged", so the existing value is kept (avoids accidental wipes)."""
    for f in fields:
        nv = getattr(new, f, None)
        if _nonempty(nv):
            setattr(existing, f, nv)


# Deliberately excludes "directive" — it is the user-written top-priority rule the AI author must not touch (kept, never cleared, when merging an existing character)
_CARD_FIELDS = ["name", "faction", "controller", "gender", "backstory", "personality", "voice",
                "motive", "tactics", "abilities", "defenses", "weaknesses"]


def apply_author_reply(sc: Scenario, rep) -> str:
    """Merge the author agent's block update into the master scenario (empty field = unchanged). Returns the name of the updated block."""
    block = rep.block
    if block == "world" and rep.world:
        _merge_fields(sc.world, rep.world, ["tone", "background", "laws"])
    elif block == "scene" and rep.scene:
        _merge_fields(sc.scene, rep.scene, ["id", "location", "hook", "present"])
    elif block == "char" and rep.char and rep.char_id:
        cid = rep.char_id
        if cid in sc.cards:
            _merge_fields(sc.cards[cid], rep.char, _CARD_FIELDS)
        else:
            sc.cards[cid] = rep.char
        if cid not in sc.scene.present:
            sc.scene.present.append(cid)
    elif block == "ledger" and rep.ledger:
        L = sc.ledger
        for cid, cl in rep.ledger.characters.items():       # key-level merge: keep characters not mentioned
            L.characters[cid] = cl
        for f in ["spatial", "scene_facts", "social_facts"]:   # replace only when non-empty
            nv = getattr(rep.ledger.scene, f)
            if _nonempty(nv):
                setattr(L.scene, f, nv)
        if _nonempty(rep.ledger.faction_private):
            L.faction_private.update(rep.ledger.faction_private)
    else:
        return "none"
    return block


def session_from_scenario(sc: Scenario) -> Session:
    """Wrap a Scenario into a fresh playable Session (deep-copies static data, initializes runtime fields).

    Fallback: present characters missing an initial ledger entry get a default one, otherwise nobody on the action bar can act and the loop never ends.
    (The player is identified by controller=="player", not a hard-coded id, so character ids never need rewriting.)
    """
    scene = sc.scene.model_copy(deep=True)
    cards = {k: v.model_copy(deep=True) for k, v in sc.cards.items()}
    ledger = sc.ledger.model_copy(deep=True)

    # present character missing initial state → add a default (player slightly faster)
    for cid in scene.present:
        if cid in cards and cid not in ledger.characters:
            spd = config.SPEED_PLAYER if cards[cid].controller == "player" else config.SPEED_NORMAL
            ledger.characters[cid] = CharLedger(speed=spd)

    memory = {cid: [] for cid in scene.present if cid in cards}
    public_log, log = [], []
    if scene.location:
        line = f"[Scene] {scene.location}"
        public_log.append(line); log.append(engine.log_system_entry(line))
    if scene.hook:
        line = f"[Opening] {scene.hook}"
        public_log.append(line); log.append(engine.log_system_entry(line))
    s = Session(
        scene=scene,
        world=sc.world.model_copy(deep=True),
        cards=cards,
        ledger=ledger,
        memory=memory,
        public_log=public_log,
        log=log,
    )
    engine.prune_orphans(s)   # drop orphan ids in present/ledger that reference missing cards, so downstream s.cards[cid] is safe
    return s
