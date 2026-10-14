"""Unit tests: engine pure logic (action bar / fog of war / two axes / delta / TTL / structured log).

A unit test exercises a single function without network or disk — the fastest and most numerous kind. Each test_*
function is one test, asserting expectations; the `sess` fixture (see conftest.py) injects a fresh tavern Session.
"""
import pytest
from backend import engine, config
from backend.models import (
    Intent, Reaction, Condition, Adjudication, LedgerDelta, DeltaItem,
)


def test_action_bar_distribution(sess):
    """Action bar: everyone gets to act, the player is most active (highest speed), and the player goes first."""
    counts = {"player": 0, "aqing": 0, "scar": 0}
    seq = []
    for _ in range(30):
        actor = engine.pick_actor(sess)
        counts[actor] += 1
        seq.append(actor)
        engine.consume_turn(sess, actor)
    assert all(v > 0 for v in counts.values()), f"someone is starved: {counts}"
    assert counts["player"] >= counts["aqing"], f"player should be most active: {counts}"
    assert seq[0] == "player", f"player should go first: {seq[:3]}"


def test_fog_hides_gm_secrets(sess):
    """Fog of war: the player's view hides gm secrets; the adjudicator's ground truth sees everything."""
    view = engine.build_view(sess, "player")
    assert "afraid of fire" not in view
    assert "waiting for his accomplices" not in view
    assert "back door is locked" in view       # public facts are visible
    assert "short blade" in view               # your own items are visible
    gt = engine.ground_truth(sess)
    assert "afraid of fire" in gt and "waiting for his accomplices" in gt


# Axis A: should we collect a reaction from the target? bound = whether scar is tied up (tied up → cannot react).
@pytest.mark.parametrize("bound, target, expected", [
    (False, "scar", "scar"),   # conscious enemy → collect a reaction
    (True,  "scar", None),     # tied up, cannot react → don't
    (False, None,   None),     # no target → don't
])
def test_needs_reaction(sess, bound, target, expected):
    if bound:
        sess.ledger.characters["scar"].status_effects.append(Condition(content="hands tied behind his back", visibility="public"))
    intent = Intent(actor="player", action="attacks him", target=target)
    assert engine.needs_reaction(sess, intent) == expected


# Axis B: is it contested (roll luck)? Actively opposed, or the environment itself is a gamble → contested.
@pytest.mark.parametrize("action, react_target, expected", [
    ("flips the table into him and attacks all-out", "scar", True),    # opposed → contested
    ("calmly steps back two paces",                  None,   False),   # calm retreat → not contested
    ("takes a running jump across the crack",        None,   True),    # environmental gamble (contested even with no opponent)
], ids=["attacked-target", "calm-retreat", "risky-leap"])
def test_is_contested(sess, action, react_target, expected):
    intent = Intent(actor="player", action=action, target=None)
    assert engine.is_contested(sess, intent, react_target) is expected


# Engine keyword lists match LLM-written English text: whole words/phrases, case-insensitive.
@pytest.mark.parametrize("action, expected", [
    ("LEAPS onto the bar", True),
    ("Vaulted over the counter", True),
    ("sneaking toward the back door", True),
    ("Grabs the oil lamp", True),
    ("dodging behind a pillar", True),
    ("pours another cup of wine", False),
    ("eyes the jumpy innkeeper", False),           # "jumpy" is not "jump"
], ids=["upper", "capitalized", "ing-form", "grab", "dodging", "calm", "no-partial-word"])
def test_risky_keywords_case_insensitive_whole_word(sess, action, expected):
    intent = Intent(actor="player", action=action, target=None)
    assert engine.is_contested(sess, intent, None) is expected


@pytest.mark.parametrize("status, can_react", [
    ("Knocked Out cold", False),
    ("Wrists BOUND with rope", False),
    ("restrained by two guards", False),
    ("Paralyzed by a pressure-point strike", False),
    ("stunned by the blow", False),
    ("Pinned under the table", False),
    ("standing by the boundary stone", True),       # "boundary" is not "bound"
    ("slightly winded", True),
], ids=["knocked-out", "bound", "restrained", "paralyzed", "stunned", "pinned", "no-partial-word", "minor"])
def test_incapacitated_keywords(sess, status, can_react):
    sess.ledger.characters["scar"].status_effects.append(Condition(content=status, visibility="public"))
    intent = Intent(actor="player", action="attacks him", target="scar")
    assert (engine.needs_reaction(sess, intent) == "scar") is can_react


@pytest.mark.parametrize("perception", ["Unconscious", "passed out", "KNOCKED OUT"])
def test_unconscious_perception_blocks_reaction(sess, perception):
    """An unconscious perception state (any casing) means the character neither perceives nor opposes."""
    sess.ledger.characters["scar"].perception = perception
    assert engine._perceives(sess, "scar") is False
    assert engine._can_oppose(sess, "scar") is False
    assert engine.needs_reaction(sess, Intent(actor="player", action="attacks him", target="scar")) is None


@pytest.mark.parametrize("content, ends", [
    ("Dead, throat cut", True),
    ("killed by the blast", True),
    ("Completely Subdued and disarmed", True),
    ("deadly calm", False),                        # "deadly" is not "dead"
    ("bleeding from the right arm", False),
    ("Dead drunk, slumped on the bar", False),     # "dead" as an intensifier
], ids=["dead", "killed", "subdued", "no-partial-word", "wounded", "dead-drunk"])
def test_check_end_keywords(sess, content, ends):
    sess.ledger.characters["scar"].conditions.append(Condition(content=content))
    result = engine.check_end(sess)
    if ends:
        assert result and result.startswith("Scar is out of the scene")
    else:
        assert result is None


def test_apply_delta(sess):
    """Adjudication delta: new states and derived fields (speed) take effect."""
    adj = Adjudication(
        outcome="success_with_cost",
        ledger_delta=LedgerDelta(add=[
            DeltaItem(subject="scar", category="conditions", content="knife wound in the right shoulder",
                      gates="can't land heavy blows with the right hand", visibility="public"),
        ]),
        speed_updates={"scar": 3},
    )
    engine.apply_delta(sess, adj)
    blob = " ".join(c.content for c in sess.ledger.characters["scar"].conditions)
    assert "knife wound in the right shoulder" in blob
    assert sess.ledger.characters["scar"].speed == 3


def test_ttl_expire(sess):
    """TTL: transients with a ttl expire automatically; persistent states (None) remain."""
    sess.turn = 5
    engine.apply_delta(sess, Adjudication(ledger_delta=LedgerDelta(add=[
        DeltaItem(subject="scar", category="conditions", content="startled back by the firelight", ttl=2),
        DeltaItem(subject="scar", category="conditions", content="serious wound to the right ribs"),  # persistent
    ])))  # created_turn=5
    blob = lambda: " ".join(c.content for c in sess.ledger.characters["scar"].conditions)
    sess.turn = 6
    engine.expire_transients(sess)
    assert "startled back by the firelight" in blob()      # 1 beat later, still there
    sess.turn = 7
    engine.expire_transients(sess)
    assert "startled back by the firelight" not in blob()  # 2 beats later, expired
    assert "serious wound to the right ribs" in blob()     # persistent, never expires


def test_gender_in_views(sess):
    """Character info: gender is injected into views and ground truth, visible to opponents (so nobody guesses)."""
    view = engine.build_view(sess, "scar")     # Scar looking at Qing
    assert "Qing (ally, male)" in view
    assert "male" in engine.ground_truth(sess)


def test_view_and_ground_truth_formatting(sess):
    """View/ground-truth text is plain English: [Scene] header, "Holding: name (state)", comma joiners."""
    view = engine.build_view(sess, "player")
    assert view.startswith("[Scene] ")
    assert "Holding: short blade (intact)" in view
    assert "player (ally, male, self)" in view
    gt = engine.ground_truth(sess)
    assert gt.startswith("[Scene] ")
    assert "  Defenses: trained in iron-body technique" in gt
    assert "  - Item quick blade: intact, right hand resting on the hilt" in gt
    inv = next(c for c in engine.known_characters(sess) if c["id"] == "player")["inventory"]
    assert inv == ["short blade (intact)"]


def test_log_entries_fog(sess):
    """Structured per-beat log: always records the actor; open actions are visible even for enemies; reaction text is still ally-only."""
    pi = Intent(actor="player", action="draws his sword and rushes the door", target="scar")
    e = engine.log_action_entry(sess, pi, None, "player", "The player draws his sword and rushes for the door.")
    assert e["actor"] == "player"
    assert e["controller"] == "player"               # "player" is decided by controller, not by id
    assert e["action_text"] == "draws his sword and rushes the door"       # ally: input attached

    ei = Intent(actor="scar", action="a fast downward slash", target="player")   # open (covert=False)
    pr = Reaction(actor="player", reaction="sidesteps and parries")
    e2 = engine.log_action_entry(sess, ei, pr, "scar", "Scar swings his blade.")
    assert e2["actor"] == "scar"
    assert e2["controller"] == "agent"            # enemy NPC controller=agent
    assert e2["action_text"] == "a fast downward slash"      # enemy **open** actions are now visible directly
    assert e2["reaction_text"] == "sidesteps and parries"      # ally reaction visible (reaction axis unchanged this round)

    sys_e = engine.log_system_entry("[Scene] tavern")
    assert sys_e["actor"] is None


def test_log_action_entry_hidden_surface(sess):
    """Cover split for covert actions (the final entry after adjudication):
    enemy gets away with it → show the cover; detected → true intent exposed; cover left blank → None (never leak the intent); ally covert → true intent (they know)."""
    ei = Intent(actor="scar", action="winks to signal his accomplice", target=None, covert=True)

    # gets away with it: show the adjudicated cover, not the true intent
    mix = engine.log_action_entry(sess, ei, None, "scar", "Scar raises his cup.",
                                  cover="raises his cup and takes a sip", detected=False)
    assert mix["action_text"] == "raises his cup and takes a sip"
    assert "signal" not in mix["action_text"]

    # detected: true intent exposed
    seen = engine.log_action_entry(sess, ei, None, "scar", "Qing sees right through it.",
                                   cover="", detected=True)
    assert seen["action_text"] == "winks to signal his accomplice"

    # the LLM left the cover blank and didn't mark it detected: degrade to None, never leak the intent
    sloppy = engine.log_action_entry(sess, ei, None, "scar", "...",
                                     cover="", detected=False)
    assert sloppy["action_text"] is None

    # ally covert action: the player is in the same faction and sees the true intent
    ally_hidden = Intent(actor="aqing", action="quietly winks at the player", target=None, covert=True)
    ah = engine.log_action_entry(sess, ally_hidden, None, "aqing", "Qing winks.",
                                 cover="", detected=False)
    assert ah["action_text"] == "quietly winks at the player"

    # neutral factions are masked as "not ally" too (regression guard: don't change the check to faction=="enemy", or neutrals leak)
    sess.cards["scar"].faction = "neutral"
    neu = engine.log_action_entry(sess, ei, None, "scar", "...", cover="leans in to chat", detected=False)
    assert neu["action_text"] == "leans in to chat" and "signal" not in neu["action_text"]


def test_log_action_entry_advance_flag(sess):
    """Time jump: non-empty time_skip → the log carries the description so the frontend draws a divider; normal beats → None."""
    pi = Intent(actor="player", action="I quickly bought it and came back", target=None)
    jumped = engine.log_action_entry(sess, pi, None, "player", "Half an hour later, the player returns carrying the goods.",
                                     time_skip="Half an hour later the player is back with the purchase")
    assert jumped["time_skip"] == "Half an hour later the player is back with the purchase"
    normal = engine.log_action_entry(sess, pi, None, "player", "The player stands still.")
    assert normal["time_skip"] is None        # default empty → None, no divider
    # preview frames (log_pending_entry uses the same gate) never carry a time skip either
    assert engine.log_pending_entry(sess, "player", pi)["time_skip"] is None


def test_log_pending_entry_fog(sess):
    """Delayed-reveal in_progress preview frame (narration not out, resolved=False):
    open actions (incl. enemy) may show early; enemy **covert** actions are never previewed before adjudication."""
    pi = Intent(actor="player", action="flips the table into him", target="scar")
    pe = engine.log_pending_entry(sess, "player", pi)
    assert pe["narration"] is None and pe["action_text"] == "flips the table into him"   # ally intent can show early

    open_foe = Intent(actor="scar", action="slashes straight down", target="player")  # open enemy action
    of = engine.log_pending_entry(sess, "scar", open_foe)
    assert of["action_text"] == "slashes straight down"                              # open enemy actions also show early

    hidden_foe = Intent(actor="scar", action="quietly draws his knife", target="player", covert=True)
    hf = engine.log_pending_entry(sess, "scar", hidden_foe)
    assert hf["actor"] == "scar" and hf["action_text"] is None          # enemy covert intent never leaks early

    r_ally = Reaction(actor="aqing", reaction="catches the knife you toss him")
    assert engine.log_pending_entry(sess, "player", pi, r_ally)["reaction_text"] == "catches the knife you toss him"
    r_foe = Reaction(actor="scar", reaction="knocks it aside with his blade")
    assert engine.log_pending_entry(sess, "player", pi, r_foe)["reaction_text"] is None  # enemy reactions don't leak (this round)


def test_perception_brief_skips_unknown_keys(sess):
    """If the LLM uses a non-existent key (a character name / made-up id) in the perception map, skip it without crashing (regression for a production KeyError)."""
    from backend import agents
    out = agents._perception_brief(sess, {"player": "all", "Kyle": "none", "scar": "partial"})
    assert "Kyle" not in out                      # unknown key skipped
    assert "player" in out and "Scar" in out      # valid keys rendered normally
    assert agents._perception_brief(sess, {"Nobody": "none"}) == "- Everyone: all"  # all invalid → default


def test_resolve_id(sess):
    """Agents use names; the program resolves them back to ids at the boundary; ids pass through, unknown → None."""
    assert engine.resolve_id(sess, "scar") == "scar"     # already an id
    assert engine.resolve_id(sess, "Scar") == "scar"     # name → id
    assert engine.resolve_id(sess, "Qing") == "aqing"
    assert engine.resolve_id(sess, "Nobody") is None
    assert engine.resolve_id(sess, None) is None


def test_target_char_by_name(sess):
    """A target given by name also resolves to an id."""
    assert engine.target_char(sess, Intent(actor="player", action="hit", target="Scar")) == "scar"
    assert engine.target_char(sess, Intent(actor="player", action="hit", target="scar")) == "scar"
    assert engine.target_char(sess, Intent(actor="player", action="hit", target="Nobody")) is None


def test_apply_delta_keys_by_name(sess):
    """Adjudication using character names as keys (subject/speed_updates/faction_changes) still lands on the right character."""
    adj = Adjudication(
        speed_updates={"Scar": 3},
        faction_changes={"Scar": "ally"},
        ledger_delta=LedgerDelta(add=[DeltaItem(subject="Scar", category="conditions", content="knife wound in the right arm")]),
    )
    engine.apply_delta(sess, adj)
    assert sess.ledger.characters["scar"].speed == 3
    assert sess.cards["scar"].faction == "ally"
    assert any("knife wound in the right arm" in c.content for c in sess.ledger.characters["scar"].conditions)


def test_apply_delta_normalizes_self_visibility(sess):
    """Adjudication writing self: visibility with a name → normalized to self:id when recorded, so self-only works."""
    adj = Adjudication(ledger_delta=LedgerDelta(add=[
        DeltaItem(subject="Scar", category="conditions", content="secretly afraid of fire", visibility="self:Scar")]))
    engine.apply_delta(sess, adj)
    cond = sess.ledger.characters["scar"].conditions[-1]
    assert cond.visibility == "self:scar"                          # name → id
    assert engine._visible(cond, "scar", "enemy") is True         # visible to self
    assert engine._visible(cond, "player", "ally") is False    # invisible to others


def test_distribute_private_by_name(sess):
    """Private narration keyed by character name is still delivered to that character."""
    engine.distribute(sess, "public narration", {"Qing": "something only Qing perceives"})
    assert sess.memory["aqing"][-1] == "something only Qing perceives"
    assert sess.memory["scar"][-1] == "public narration"


def test_player_id_by_role(sess):
    """The player is identified by controller=="player", not a hard-coded id."""
    assert engine.player_id(sess) == "player"      # the tavern player happens to have id=player
    sess.cards["player"].controller = "agent"
    sess.cards["aqing"].controller = "player"
    assert engine.player_id(sess) == "aqing"       # after switching controller it's aqing, regardless of id


def test_session_autofills_ledger_no_id_rewrite():
    """Reproduces the scenario shape that used to hang: player id != 'player' + empty ledger.characters → state filled in, id not rewritten, playable without hanging."""
    from backend.models import Scenario, CharCard, Scene
    from backend import scenario as scen
    sc = Scenario(id="t", scene=Scene(id="s", present=["lilatya"]),
                  cards={"lilatya": CharCard(name="0", faction="ally", controller="player")})
    s = scen.session_from_scenario(sc)
    assert "lilatya" in s.cards and "player" not in s.cards   # id not rewritten
    assert s.scene.present == ["lilatya"]
    assert "lilatya" in s.ledger.characters                   # initial state auto-filled
    assert engine.player_id(s) == "lilatya"                   # player identified by controller
    assert engine.pick_actor(s) == "lilatya"                  # no hang, recognized as the player


def test_pick_actor_empty_raises(sess):
    """Empty ledger.characters raises immediately instead of looping forever."""
    sess.ledger.characters = {}
    with pytest.raises(ValueError):
        engine.pick_actor(sess)


def test_beats_to_act():
    """The program computes "beats until the threshold": a negative starting gauge → many beats away (simulating a slow approach)."""
    from backend.models import CharLedger
    assert engine.beats_to_act(CharLedger(speed=5, gauge=0)) == 4       # ceil(20/5)
    assert engine.beats_to_act(CharLedger(speed=5, gauge=-40)) == 12    # ceil(60/5)
    assert engine.beats_to_act(CharLedger(speed=5, gauge=20)) == 0      # already at the threshold
    assert engine.beats_to_act(CharLedger(speed=7, gauge=0)) == 3       # ceil(20/7)


def test_action_order_slow_arriver_last(sess):
    """A character with a negative starting gauge (simulating slowly approaching reinforcements) is last in turn order with the most beats."""
    sess.ledger.characters["scar"].gauge = -40
    order = engine.action_order(sess)
    assert [t[0] for t in order][-1] == "scar"   # the slow one is last
    assert order[-1][3] > order[0][3]            # beats increase
    assert order[-1][3] >= 12                     # scar is about 12 beats out (slow approach)


def test_faction_mates(sess):
    """Same faction sees each other (present, excluding self); other factions excluded."""
    assert engine.faction_mates(sess, "player") == ["aqing"]   # ally teammate (scar = enemy, excluded)
    assert engine.faction_mates(sess, "scar") == []            # the enemy side has only one


def test_apply_delta_faction_change(sess):
    """Adjudicated faction changes update the card's faction in place (defect/join), affecting same-faction checks."""
    assert sess.cards["scar"].faction == "enemy"
    engine.apply_delta(sess, Adjudication(faction_changes={"scar": "ally"}))
    assert sess.cards["scar"].faction == "ally"
    assert "scar" in engine.faction_mates(sess, "player")      # after defecting he's an ally teammate


def test_mates_brief_full_card_same_faction_only(sess):
    """Same-faction teammate cards include weaknesses; nothing leaks across factions."""
    from backend import agents
    engine.apply_delta(sess, Adjudication(faction_changes={"scar": "ally"}))
    brief = agents._mates_brief(sess, "player")
    assert "Scar" in brief and "afraid of fire" in brief          # ally teammates get the full card (incl. weaknesses)
    engine.apply_delta(sess, Adjudication(faction_changes={"scar": "enemy"}))
    assert "afraid of fire" not in agents._mates_brief(sess, "player")    # enemy details don't leak


def test_remove_skips_empty_key(sess):
    """An empty string in remove must be skipped, not wipe the whole list (the "" in content is always true trap); real keywords still remove."""
    cl = sess.ledger.characters["scar"]
    cl.conditions = [Condition(content="knife wound in the right arm"), Condition(content="face gone pale")]
    engine.apply_delta(sess, Adjudication(ledger_delta=LedgerDelta(remove=["", "knife wound in the right arm"])))
    blobs = {c.content for c in cl.conditions}
    assert "knife wound in the right arm" not in blobs        # real keyword removed normally
    assert "face gone pale" in blobs                          # the empty string didn't wipe the list
