"""Data models: world + two-layer state + structured I/O for each agent.

Design reference: docs/design.md
- world (static): tone / background / laws (hard rules that bind adjudication)
- Layer 1, cards (static): role-play fields + adjudication traits (hidden from opponents)
- Layer 2, ledger (dynamic, modified only by adjudication deltas): includes social_facts
- LLM I/O: intent / reaction / adjudication dual output / narration
Field names line up with the design doc and the prompts.
"""
from __future__ import annotations
from typing import Optional, Dict, List
from pydantic import BaseModel, Field


# ───────────────── world (static) ─────────────────
class World(BaseModel):
    tone: str = ""                                   # genre/mood → GM voice, character grounding
    background: str = ""                                   # ~200-word setting → grounds every agent
    laws: List[str] = Field(default_factory=list)     # hard rules that bind adjudication


# ───────────────── state entries ─────────────────
class Condition(BaseModel):
    content: str
    gates: str = ""                 # how this constrains later actions (written by adjudication)
    severity: Optional[str] = None       # tipsy/drunk/blind drunk, light wound/serious wound/dying
    visibility: str = "public"           # public | gm | faction:ally | self:<id>
    source: str = ""
    lifetime: str = ""
    ttl: Optional[int] = None    # None = persistent; int = auto-expires after N beats (transient)
    created_turn: Optional[int] = None    # stamped by the program; used with ttl for expiry


class Item(BaseModel):
    name: str
    kind: str = ""
    traits: List[str] = Field(default_factory=list)   # stable
    state: str = "intact"                                  # mutable: intact → chipped → broken
    location: str = ""                                      # mutable: right hand → on the floor


# ───────────────── Layer 1: cards (static) ─────────────────
class CharCard(BaseModel):
    name: str
    faction: str                              # ally / enemy / neutral
    controller: str = "agent"                    # "player" | "agent"
    gender: str = ""                         # basic info opponents can observe (shown in views/roster so nobody guesses)
    # ── role-play (read by the character agent and the owner; hidden from opponents) ──
    backstory: str = ""                      # origin, history, profession
    directive: str = ""                      # user-written top-priority persona rule (fallback/debugging): overrides the rest of the persona but never the game rules or output format; fed only to the character agent, the AI author never touches it
    personality: List[str] = Field(default_factory=list)
    voice: str = ""                      # tone/catchphrases/word choice, so dialogue is distinctive
    motive: str = ""                      # what they want this scene; drives their choices
    tactics: List[str] = Field(default_factory=list)   # habitual methods: brute force/dirty tricks/negotiation/stalling/taunting…
    # ── adjudication (fully visible to the adjudicator; hidden from opponents, may be secret) ──
    abilities: List[str] = Field(default_factory=list)        # what they're good at (qualitative)
    defenses: List[str] = Field(default_factory=list)     # e.g. "iron-body training, ordinary blows barely hurt", "impervious to blades"
    weaknesses: List[str] = Field(default_factory=list)         # e.g. "afraid of fire", "old wound on the left ribs", "greedy, can be bought"


# ───────────────── Layer 2: ledger (dynamic) ─────────────────
class CharLedger(BaseModel):
    posture: str = ""
    conditions: List[Condition] = Field(default_factory=list)   # injuries/physical/emotional/attitudes toward others
    status_effects: List[Condition] = Field(default_factory=list)   # bound/unconscious/incapacitated
    items: Dict[str, Item] = Field(default_factory=dict)
    carried: List[Condition] = Field(default_factory=list)        # persistent (reserved for v1)
    # ── derived fields (maintained by adjudication, read-only for the program) ──
    speed: int = 5
    perception: str = "normal"
    gauge: int = 0


class SceneLedger(BaseModel):
    spatial: List[Condition] = Field(default_factory=list)
    scene_facts: List[Condition] = Field(default_factory=list)     # environment + revealed intel (visibility controls who knows)
    social_facts: List[Condition] = Field(default_factory=list)     # promises/deals/alliances/truces/confessions (with gates and visibility)


class Ledger(BaseModel):
    characters: Dict[str, CharLedger] = Field(default_factory=dict)
    scene: SceneLedger = Field(default_factory=SceneLedger)
    faction_private: Dict[str, Dict[str, List[str]]] = Field(default_factory=dict)  # {"ally":{"plans":[...]}}


class Scene(BaseModel):
    id: str
    location: str = ""
    hook: str = ""
    present: List[str] = Field(default_factory=list)


class Session(BaseModel):
    scene: Scene
    world: World = Field(default_factory=World)
    cards: Dict[str, CharCard]
    ledger: Ledger
    memory: Dict[str, List[str]] = Field(default_factory=dict)   # each character's recent verbatim narration (rolling window)
    summary: Dict[str, str] = Field(default_factory=dict)          # each character's rolling "story so far" summary
    public_log: List[str] = Field(default_factory=list)           # narration stream shown to the player (plain text; for memory/adjudication/backward compat)
    log: List[dict] = Field(default_factory=list)              # structured per beat: {narration,actor,actor_name,faction,action_text (gated by visible_action_text),reaction_text (ally)…}
    turn: int = 0
    pending: Optional[dict] = None                            # state while waiting on the player
    ended: Optional[str] = None                                # why the game ended
    in_progress: Optional[dict] = Field(default=None, exclude=True)  # transient: visible parts of the current beat already revealed (action/reaction, narration not out yet); exclude=True guarantees it is never persisted


class Scenario(BaseModel):
    """A scenario = the static/initial part of a Session (no runtime fields). Serializable to JSON.
    Fields have defaults so half-finished drafts still validate during authoring."""
    id: str = "scenario"
    world: World = Field(default_factory=World)
    scene: Scene = Field(default_factory=lambda: Scene(id="scene"))
    cards: Dict[str, CharCard] = Field(default_factory=dict)
    ledger: Ledger = Field(default_factory=Ledger)


# ───────────────── LLM I/O ─────────────────
class Intent(BaseModel):
    """A character's / the player's action intent (only what they want to do, never whether it succeeds)."""
    actor: str = ""
    action: str                          # one sentence: what they want to do (including how)
    target: Optional[str] = None         # char_id or None
    covert: bool = False                 # wants to hide it from enemies (adjudication splits cover vs. true intent)
    faction_switch: Optional[str] = None      # proposes defecting/joining a faction (ally/enemy/neutral); adjudication decides whether it takes effect


class Reaction(BaseModel):
    """The targeted character's response intent (an intent, not a verdict; may defend/counter/retort/shout them down…)."""
    actor: str = ""
    reaction: str                          # one sentence: how you respond (including how)


class DeltaItem(BaseModel):
    subject: str                          # char_id or "scene"
    category: str                          # posture/conditions/status_effects/item_state/spatial/scene_facts/social_facts/intel
    content: str
    gates: str = ""
    severity: Optional[str] = None
    visibility: str = "public"
    ttl: Optional[int] = None      # 1-3 for transient; null for persistent state


class LedgerDelta(BaseModel):
    add: List[DeltaItem] = Field(default_factory=list)
    remove: List[str] = Field(default_factory=list)    # removed by matching a content keyword
    modify: List[DeltaItem] = Field(default_factory=list)


class Adjudication(BaseModel):
    """Adjudication dual output: action ruling + knowledge ruling."""
    # A. action ruling
    relevant_conditions: List[str] = Field(default_factory=list)
    rulings: List[str] = Field(default_factory=list)
    feasibility: str = "feasible"               # impossible/hindered/feasible/needs_rewrite
    outcome: str = "success_with_cost"       # success/success_with_cost/reversal
    ledger_delta: LedgerDelta = Field(default_factory=LedgerDelta)
    speed_updates: Dict[str, int] = Field(default_factory=dict)
    perception_updates: Dict[str, str] = Field(default_factory=dict)
    faction_changes: Dict[str, str] = Field(default_factory=dict)   # char_id → new faction; defections/recruitments approved by adjudication
    # B. knowledge ruling
    perception_map: Dict[str, str] = Field(default_factory=dict)  # char_id -> all/partial:.../none
    # cover split for covert actions (only meaningful when this beat's action has covert=True)
    detected: bool = False                # whether the covert action was seen through; True = exposed, False = got away with it
    cover: str = ""                    # when covert and NOT detected, the innocent-looking action bystanders see; empty if detected or not covert
    # C. time_skip (non-combat advance: a time jump) — the anti-stalemate lever for low-conflict scenes
    time_skip: str = ""                    # non-empty = this beat triggers a time jump; the text describes the compressed time (e.g. "Half an hour later Chloe comes back carrying ice cream"); empty = no jump. Narration uses it to skip dead time; characters stay in the scene
    # D. for the GM
    gm_summary: str = ""


class Narration(BaseModel):
    public: str
    private: Dict[str, str] = Field(default_factory=dict)     # char_id -> private narration


class Summary(BaseModel):
    summary: str


class CleanCond(BaseModel):
    content: str
    gates: str = ""
    visibility: str = "public"


class ConsolidateOut(BaseModel):
    conditions: List[CleanCond] = Field(default_factory=list)


class AuthorReply(BaseModel):
    """Author agent output each turn: one reply + at most one block update."""
    reply: str                                # message to the user (a question / what changed)
    block: str = "none"                         # world / scene / char / ledger / none (question only)
    char_id: Optional[str] = None             # which character, when block=char
    world: Optional[World] = None
    scene: Optional[Scene] = None
    char: Optional[CharCard] = None
    ledger: Optional[Ledger] = None
    missing: List[str] = Field(default_factory=list)   # still missing / undecided
    done: bool = False                        # complete enough to save
