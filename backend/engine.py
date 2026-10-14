"""Core engine (pure logic, no API calls): action bar, two-axis checks, fog-of-war filtering, delta application.

These are all unit-testable pure functions; agent calls live in agents.py and orchestration in flow.py.
"""
import random
import re
from typing import List, Optional, Tuple
from .models import Session, Condition, DeltaItem, LedgerDelta, Adjudication
from . import config

PLAYER = "player"

# Keywords below match LLM-written condition/action text: whole words or phrases, case-insensitive.
# Perception states that mean a character perceives nothing
UNCONSCIOUS_KW = ("unconscious", "knocked out", "passed out", "fainted", "out cold", "comatose")
# Keywords that mean "cannot react / incapacitated"
INCAPACITATED_KW = UNCONSCIOUS_KW + (
    "bound", "tied", "restrained", "shackled", "paralyzed", "paralysed",
    "stunned", "subdued", "pinned", "immobilized", "incapacitated",
)
# Environmental-risk keywords (a gamble even with no opponent)
RISKY_KW = (
    "jump", "jumps", "jumped", "jumping",
    "leap", "leaps", "leapt", "leaped", "leaping",
    "climb", "climbs", "climbed", "climbing",
    "sneak", "sneaks", "sneaked", "sneaking", "snuck",
    "gamble", "gambles", "gambled", "gambling",
    "grab", "grabs", "grabbed", "grabbing",
    "snatch", "snatches", "snatched", "snatching",
    "vault", "vaults", "vaulted", "vaulting",
    "lunge", "lunges", "lunged", "lunging",
    "pounce", "pounces", "pounced", "pouncing",
    "dodge", "dodges", "dodged", "dodging",
)
# Keywords that take a character out of the scene (end condition)
END_KW = ("dead", "died", "killed", "slain", "deceased",
          "bound beyond escape", "hopelessly bound", "completely subdued", "fully subdued")


def _kw_regex(words) -> "re.Pattern":
    return re.compile(r"\b(?:" + "|".join(re.escape(w) for w in words) + r")\b", re.IGNORECASE)


_UNCONSCIOUS_RE = _kw_regex(UNCONSCIOUS_KW)
_INCAPACITATED_RE = _kw_regex(INCAPACITATED_KW)
_RISKY_RE = _kw_regex(RISKY_KW)
# "dead" as an intensifier ("dead drunk", "dead tired") must not end the scene
_END_RE = re.compile(_kw_regex(END_KW).pattern.replace(
    r"dead", r"dead(?!\s+(?:drunk|tired|silent|quiet|still|serious|set|calm))", 1), re.IGNORECASE)


def resolve_id(s: Session, key) -> Optional[str]:
    """Resolve a character "name or id" given by the LLM back to a char_id.

    Design: agents always see/use character names; the program converts back to ids only at the
    operation boundary, via this function. Accepts: already an id → as is; a character's name → that id;
    no match → None."""
    if not key:
        return None
    if key in s.cards:                       # already an id
        return key
    for cid, c in s.cards.items():            # match by name (names should be unique)
        if c.name == key:
            return cid
    return None


def player_id(s: Session) -> str:
    """Player character id: identified by the semantic field controller=="player", **never a hard-coded id**. Falls back to PLAYER."""
    for cid, c in s.cards.items():
        if c.controller == "player":
            return cid
    return PLAYER


def prune_orphans(s: Session) -> None:
    """Drop orphan ids in present / ledger that reference non-existent character cards (in place).

    Guarantees the invariants present ⊆ cards and ledger character keys ⊆ cards, so the bare
    `s.cards[cid]` lookups downstream (ground_truth / build_view / flow upkeep…) never KeyError on an
    inconsistent scenario. Called from both entry points: new game and load game."""
    s.scene.present = [cid for cid in s.scene.present if cid in s.cards]
    s.ledger.characters = {cid: cl for cid, cl in s.ledger.characters.items() if cid in s.cards}


def validate_playable(s: Session) -> Optional[str]:
    """Pre-game playability check: returns the reason the scenario is unplayable, or None if playable.

    Turns two kinds of incomplete scenarios that would crash/hang new_game into a clear rejection
    (instead of a 500 or an infinite loop):
      1. No character with an action bar → pick_actor has nobody to move (used to ValueError → 500).
      2. No controller=="player", or the player isn't present → advance never reaches the player and never stops (used to loop the LLM forever).
    """
    if not s.ledger.characters:
        return "no characters are present (add at least one character to the scene's present list)"
    players = [cid for cid, c in s.cards.items() if c.controller == "player"]
    if not players:
        return "missing a player character (set one character's controller to player)"
    if not any(pid in s.ledger.characters for pid in players):
        return "the player character is not present (add the player character to the scene's present list)"
    return None


# ───────────────── action bar ─────────────────
def _tick(s: Session) -> None:
    for cl in s.ledger.characters.values():
        cl.gauge += cl.speed


def pick_actor(s: Session) -> str:
    """Each call first advances one beat; if nobody has reached the threshold, keep ticking until someone does. Returns the actor id."""
    actors = s.ledger.characters
    if not actors:                            # nobody has an initial state → otherwise the loop below never ends
        raise ValueError("No character can act: ledger.characters is empty (scenario is missing initial state)")
    _tick(s)  # "every time someone acts, everyone ticks once"
    safety = 0
    while not any(cl.gauge >= config.ACTION_THRESHOLD for cl in actors.values()):
        _tick(s)
        safety += 1
        if safety > 100000:                   # fallback: all speeds <= 0 or similar; never loop forever
            break
    ready = [cid for cid, cl in actors.items()
             if cl.gauge >= config.ACTION_THRESHOLD]
    if not ready:                             # nobody reached the threshold (abnormal) → take the highest gauge
        ready = [max(actors, key=lambda c: actors[c].gauge)]
    # Order purely by gauge: highest goes first; ties keep the natural present/dict order
    # (max returns the first maximum on ties, i.e. natural order — the player no longer wins ties unconditionally)
    return max(ready, key=lambda c: actors[c].gauge)


def consume_turn(s: Session, actor: str) -> None:
    s.ledger.characters[actor].gauge -= config.ACTION_THRESHOLD   # subtract the threshold, keep the overflow


def beats_to_act(cl, threshold: int = config.ACTION_THRESHOLD) -> int:
    """How many beats until this character reaches the action threshold (computed by the program; a negative starting gauge → many beats away, simulating a slow approach)."""
    spd = max(cl.speed, 1)
    need = max(threshold - cl.gauge, 0)
    return (need + spd - 1) // spd


def action_order(s: Session) -> list:
    """Present characters sorted by beats until their turn: [(cid, name, faction, beats)…]. Lets agents see turn order and who is closing in."""
    rows = []
    for cid in s.scene.present:
        cl = s.ledger.characters.get(cid)
        if cl is None or cid not in s.cards:
            continue
        rows.append((cid, s.cards[cid].name, s.cards[cid].faction, beats_to_act(cl)))
    rows.sort(key=lambda t: (t[3], -s.ledger.characters[t[0]].gauge))
    return rows


# ───────────────── perception / two axes ─────────────────
def _perceives(s: Session, who: str) -> bool:
    cap = s.ledger.characters[who].perception
    return not _UNCONSCIOUS_RE.search(cap or "")


def _can_oppose(s: Session, who: str) -> bool:
    cl = s.ledger.characters[who]
    if _UNCONSCIOUS_RE.search(cl.perception or ""):
        return False
    blob = " ".join(c.content for c in cl.status_effects)
    return not _INCAPACITATED_RE.search(blob)


def target_char(s: Session, intent) -> Optional[str]:
    t = resolve_id(s, intent.target)            # the target may be a name or an id; resolve to an id
    if t and t in s.ledger.characters and t != intent.actor:
        return t
    return None


def needs_reaction(s: Session, intent) -> Optional[str]:
    """Axis A: should we collect a reaction from some character? Returns that character's id or None.
    Gate: the target is a character ∧ (is the player ∨ (can perceive ∧ can oppose)). When in doubt, ask."""
    tgt = target_char(s, intent)
    if not tgt:
        return None
    if tgt == player_id(s):
        return tgt                          # always ask the player
    if _perceives(s, tgt) and _can_oppose(s, tgt):
        return tgt
    return None


def is_contested(s: Session, intent, reaction_target: Optional[str]) -> bool:
    """Axis B: is this contested (roll luck)? Actively opposed, or the environment itself is a gamble."""
    if reaction_target:
        return True
    return bool(_RISKY_RE.search(intent.action or ""))


def roll_luck() -> str:
    return random.choices(config.LUCK_TIERS, weights=config.LUCK_WEIGHTS, k=1)[0]


# ───────────────── fog of war: the view text a given character can see ─────────────────
def _visible(cond: Condition, viewer: str, faction: str) -> bool:
    v = cond.visibility
    if v == "public":
        return True
    if v == "gm":
        return False
    if v.startswith("faction:"):
        return v.split(":", 1)[1] == faction
    if v.startswith("self:"):
        return v.split(":", 1)[1] == viewer
    return True


def _fmt_conds(conds: List[Condition], viewer: str, faction: str) -> List[str]:
    out = []
    for c in conds:
        if not _visible(c, viewer, faction):
            continue
        g = f" ({c.gates})" if c.gates else ""
        d = f"[{c.severity}]" if c.severity else ""
        out.append(f"{c.content}{d}{g}")
    return out


def build_view(s: Session, viewer: str) -> str:
    """Build the situation text the viewer can see (fed to the character agent). Preserves fog of war."""
    faction = s.cards[viewer].faction
    lines = [f"[Scene] {s.scene.location}"]

    # public scene facts
    facts = _fmt_conds(s.ledger.scene.scene_facts, viewer, faction) \
        + _fmt_conds(s.ledger.scene.spatial, viewer, faction)
    if facts:
        lines.append("[Surroundings] " + "; ".join(facts))
    social = _fmt_conds(s.ledger.scene.social_facts, viewer, faction)
    if social:
        lines.append("[Agreements/Intel] " + "; ".join(social))

    # characters (self sees everything; others only public + visible)
    for cid, cl in s.ledger.characters.items():
        if cid not in s.scene.present:
            continue
        card = s.cards[cid]
        g = f", {card.gender}" if card.gender else ""
        self_mark = ", self" if cid == viewer else ""   # not "you" — "you" is reserved for narration addressing the player
        seg = [f"{card.name} ({card.faction}{g}{self_mark}): {cl.posture or 'present'}"]
        body = _fmt_conds(cl.conditions, viewer, faction) + _fmt_conds(cl.status_effects, viewer, faction)
        if cid == viewer:                    # you can see your own carried state and items
            body += _fmt_conds(cl.carried, viewer, faction)
            if cl.items:
                body.append("Holding: " + ", ".join(f"{it.name} ({it.state})" for it in cl.items.values()))
        if body:
            seg.append("; ".join(body))
        lines.append(" | ".join(seg))

    # faction-private plans
    plans = s.ledger.faction_private.get(faction, {}).get("plans", [])
    if plans:
        lines.append("[Our Plans] " + "; ".join(plans))

    return "\n".join(lines)


def player_situation(s: Session, viewer: Optional[str] = None) -> dict:
    """Environment and social state visible to the player (fog-filtered): scene/surroundings/intel/plans. Structured for the frontend."""
    viewer = viewer or player_id(s)
    fac = s.cards[viewer].faction
    sc = s.ledger.scene
    return {
        "scene": s.scene.location,
        "surroundings": _fmt_conds(sc.scene_facts, viewer, fac) + _fmt_conds(sc.spatial, viewer, fac),
        "intel": _fmt_conds(sc.social_facts, viewer, fac),
        "plans": list(s.ledger.faction_private.get(fac, {}).get("plans", [])),
    }


def known_characters(s: Session, viewer: Optional[str] = None) -> list:
    """Present characters as the player knows them (structured).
    - Same faction (incl. self): the full card — abilities/defenses/weaknesses/motive etc.; teammates know each other.
    - Enemies: visible state only — their secrets must be discovered through play, so they are not injected.
    """
    viewer = viewer or player_id(s)
    fac = s.cards[viewer].faction
    out = []
    for cid in s.scene.present:
        cl = s.ledger.characters.get(cid)
        if cid not in s.cards or cl is None:
            continue
        card = s.cards[cid]
        ally = card.faction == fac
        item = {
            "id": cid, "name": card.name, "faction": card.faction, "gender": card.gender,
            "is_self": cid == viewer, "is_ally": ally,
            "posture": cl.posture, "speed": cl.speed, "perception": cl.perception,
            "state": _fmt_conds(cl.conditions, viewer, fac) + _fmt_conds(cl.status_effects, viewer, fac),
        }
        if ally:                                  # allies know each other's details
            item.update({
                "backstory": card.backstory, "personality": card.personality, "voice": card.voice,
                "motive": card.motive, "tactics": card.tactics,
                "abilities": card.abilities, "defenses": card.defenses, "weaknesses": card.weaknesses,
            })
            if cid == viewer and cl.items:         # you can see your own items
                item["inventory"] = [f"{it.name} ({it.state})" for it in cl.items.values()]
        out.append(item)
    return out


def faction_mates(s: Session, cid: str) -> List[str]:
    """Other present characters in cid's faction (same faction sees each other's full card; other factions excluded)."""
    me = s.cards.get(cid)
    if not me:
        return []
    return [oid for oid in s.scene.present
            if oid != cid and oid in s.cards and s.cards[oid].faction == me.faction]


def ground_truth(s: Session) -> str:
    """Complete ground truth for adjudication (everything visible, including gm secrets)."""
    lines = [f"[Scene] {s.scene.location}"]
    for c in s.ledger.scene.scene_facts + s.ledger.scene.spatial + s.ledger.scene.social_facts:
        tag = "" if c.visibility == "public" else f" <{c.visibility}>"
        g = f" ({c.gates})" if c.gates else ""
        lines.append(f"- {c.content}{g}{tag}")
    for cid, cl in s.ledger.characters.items():
        card = s.cards.get(cid)
        if card is None:                      # defensive: orphan ledger entry (prune_orphans already cleans these; belt and braces for the adjudication path)
            continue
        g = f"/{card.gender}" if card.gender else ""
        lines.append(f"* {card.name} ({card.faction}{g}) speed {cl.speed} perception: {cl.perception}")
        if card.abilities:
            lines.append(f"  Abilities: {', '.join(card.abilities)}")
        if card.defenses:
            lines.append(f"  Defenses: {', '.join(card.defenses)}")
        if card.weaknesses:
            lines.append(f"  Weaknesses: {', '.join(card.weaknesses)}")
        lines.append(f"  Posture: {cl.posture}")
        for c in cl.conditions + cl.status_effects + cl.carried:
            tag = "" if c.visibility == "public" else f" <{c.visibility}>"
            g = f" ({c.gates})" if c.gates else ""
            lines.append(f"  - {c.content}{g}{tag}")
        for it in cl.items.values():
            lines.append(f"  - Item {it.name}: {it.state}, {it.location}")
    return "\n".join(lines)


# ───────────────── apply the adjudication delta (defensive, never crashes) ─────────────────
def _normalize_vis(s: Session, vis: str) -> str:
    """In visibility self:<X>, X may be a name (agents use names) → resolve to an id, otherwise self-only state never matches.
    faction:<faction> uses a faction value (ally/enemy/neutral), not a name, so no resolution is needed."""
    if vis and vis.startswith("self:"):
        cid = resolve_id(s, vis.split(":", 1)[1])
        if cid:
            return f"self:{cid}"
    return vis


def _to_cond(s: Session, d: DeltaItem, turn: int) -> Condition:
    return Condition(content=d.content, gates=d.gates, severity=d.severity,
                     visibility=_normalize_vis(s, d.visibility), source="adjudication",
                     ttl=d.ttl, created_turn=turn)


def _remove_matching(conds: List[Condition], key: str) -> List[Condition]:
    return [c for c in conds if key not in c.content]


def apply_delta(s: Session, adj: Adjudication) -> None:
    delta = adj.ledger_delta
    turn = s.turn
    # add
    for d in delta.add:
        cond = _to_cond(s, d, turn)
        if d.subject == "scene":
            if d.category == "spatial":
                s.ledger.scene.spatial.append(cond)
            elif d.category in ("social_facts", "promise", "agreement", "alliance", "truce"):
                s.ledger.scene.social_facts.append(cond)
            else:
                s.ledger.scene.scene_facts.append(cond)
        else:
            bid = resolve_id(s, d.subject)        # the subject may be a name or an id
            if bid and bid in s.ledger.characters:
                cl = s.ledger.characters[bid]
                if d.category == "posture":
                    cl.posture = d.content
                elif d.category == "status_effects":
                    cl.status_effects.append(cond)
                else:
                    cl.conditions.append(cond)
    # remove (keyword match; skip empty strings — "" in content is always true and would wipe the whole list)
    for key in delta.remove:
        if not key:
            continue
        for cl in s.ledger.characters.values():
            cl.conditions = _remove_matching(cl.conditions, key)
            cl.status_effects = _remove_matching(cl.status_effects, key)
        s.ledger.scene.scene_facts = _remove_matching(s.ledger.scene.scene_facts, key)
        s.ledger.scene.spatial = _remove_matching(s.ledger.scene.spatial, key)
        s.ledger.scene.social_facts = _remove_matching(s.ledger.scene.social_facts, key)
    # modify (simplified: treated as adding a new condition)
    for d in delta.modify:
        bid = resolve_id(s, d.subject)
        if bid and bid in s.ledger.characters:
            s.ledger.characters[bid].conditions.append(_to_cond(s, d, turn))
    # derived-field updates (keys may be names or ids; resolve_id for all)
    for k, sp in adj.speed_updates.items():
        cid = resolve_id(s, k)
        if cid and cid in s.ledger.characters:
            s.ledger.characters[cid].speed = sp
    for k, cap in adj.perception_updates.items():
        cid = resolve_id(s, k)
        if cid and cid in s.ledger.characters:
            s.ledger.characters[cid].perception = cap
    # faction_changes (defect/join/turned): change the card's faction in place; affects same-faction visibility from now on
    for k, fac in adj.faction_changes.items():
        cid = resolve_id(s, k)
        if cid and fac:
            s.cards[cid].faction = fac


# ───────────────── structured log entries (actor + ally input text, for the frontend) ─────────────────
def log_system_entry(text: str) -> dict:
    """System line (scene/opening/ended): no actor."""
    return {"narration": text, "actor": None, "actor_name": None, "faction": None, "controller": None,
            "action_text": None, "reaction_text": None, "reactor_name": None}


def visible_action_text(intent, ally: bool, cover: str = "",
                        detected: bool = False, resolved: bool = True) -> Optional[str]:
    """The character's visible action the player sees on the action chip (gated on covert or not). Truth table:

      open (not covert), any faction / any time       → true intent (intent.action)   # incl. enemies and preview frames
      covert + actor is ally                          → true intent                    # same faction as the player, they know
      covert + not ally + before adjudication (preview) → None                       # enemy covert actions are not previewed
      covert + not ally + after adjudication + detected → true intent                # cover blown, the truth is exposed
      covert + not ally + after adjudication + undetected → cover or None            # got away with it, show the cover; never leak the intent even if adjudication left it blank

    Note: this gate decides what to *show* (cover vs. intent); checks like is_contested always use the true intent (intent.action). The two are deliberately separate."""
    if not getattr(intent, "covert", False):
        return intent.action
    if ally:
        return intent.action
    if not resolved:
        return None
    if detected:
        return intent.action
    return cover or None


def log_action_entry(s: Session, intent, reaction, actor: str, narration: str,
                     cover: str = "", detected: bool = False, resolved: bool = True,
                     time_skip: str = "") -> dict:
    """Structured record of one beat: always records the actor; action text is gated by visible_action_text
    (open actions are visible even for enemies; enemy covert actions are hidden before adjudication, then show the cover, or the true intent only if detected). Reaction text is still ally-only.
    A non-empty time_skip means this beat contains a time jump; the frontend draws a "time passes" divider."""
    card = s.cards.get(actor)
    ally = bool(card and card.faction == "ally")
    e = {
        "narration": narration,
        "actor": actor,
        "actor_name": card.name if card else actor,
        "faction": card.faction if card else "",
        "controller": card.controller if card else "",   # "player"/"agent" — used to tell whether this is the player (not by id)
        "action_text": visible_action_text(intent, ally, cover, detected, resolved),
        "reaction_text": None,
        "reactor_name": None,
        "time_skip": time_skip or None,             # time-jump description (divider only when non-empty); None for preview frames/normal beats
    }
    if reaction is not None:
        rc = s.cards.get(reaction.actor)
        if rc and rc.faction == "ally":
            e["reaction_text"] = reaction.reaction
            e["reactor_name"] = rc.name
    return e


def log_pending_entry(s: Session, actor: str, intent, reaction=None) -> dict:
    """A beat in progress (narration not out yet, narration=None): same gate as log_action_entry but resolved=False
    — so enemy covert actions are never previewed before adjudication, while open actions (incl. enemy) and ally actions show early."""
    return log_action_entry(s, intent, reaction, actor, None, resolved=False)


# ───────────────── distribute narration (GM writes, program delivers) ─────────────────
def distribute(s: Session, public: str, private: dict) -> None:
    s.public_log.append(public)
    # private narration keys may be character names (agents use names); resolve to ids, then deliver per character
    by_id = {}
    for k, v in (private or {}).items():
        cid = resolve_id(s, k)
        if cid:
            by_id[cid] = v
    for cid in s.scene.present:
        msg = by_id.get(cid) or public
        s.memory.setdefault(cid, []).append(msg)


# ───────────────── ledger cleanup: transient TTL expiry ─────────────────
def _alive(c: Condition, turn: int) -> bool:
    if c.ttl is None or c.created_turn is None:
        return True
    return (turn - c.created_turn) < c.ttl


def expire_transients(s: Session) -> None:
    """Remove expired transient states (ttl used up). Called at the end of every beat."""
    turn = s.turn
    for cl in s.ledger.characters.values():
        cl.conditions = [c for c in cl.conditions if _alive(c, turn)]
        cl.status_effects = [c for c in cl.status_effects if _alive(c, turn)]
    sc = s.ledger.scene
    sc.scene_facts = [c for c in sc.scene_facts if _alive(c, turn)]
    sc.spatial = [c for c in sc.spatial if _alive(c, turn)]
    sc.social_facts = [c for c in sc.social_facts if _alive(c, turn)]


# ───────────────── end conditions ─────────────────
def check_end(s: Session) -> Optional[str]:
    for cid, cl in s.ledger.characters.items():
        blob = " ".join(c.content for c in cl.conditions + cl.status_effects)
        if _END_RE.search(blob):
            return f"{s.cards[cid].name} is out of the scene: {blob}"
    return None
