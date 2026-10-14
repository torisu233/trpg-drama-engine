"""Scenario save/convert + author merge (empty fields don't wipe) + degrading incomplete scenarios and the game-start gate."""
import json
from backend.models import Scenario, Scene, AuthorReply, World, CharCard, Ledger, CharLedger
from backend import scenario as scen, engine, config
from backend.scene import new_tavern_session


def test_scenario_roundtrip():
    """Session → Scenario → JSON → Scenario → Session round-trips losslessly; runtime fields are initialized correctly."""
    s0 = new_tavern_session()
    sc = scen.scenario_from_session(s0, "tavern")
    sc2 = Scenario(**json.loads(sc.model_dump_json()))
    s1 = scen.session_from_scenario(sc2)
    assert "afraid of fire" in "".join(s1.cards["scar"].weaknesses)
    assert s1.cards["aqing"].gender == "male"
    assert any("waiting for his accomplices" in c.content for c in s1.ledger.scene.scene_facts)
    assert s1.ledger.characters["player"].speed == config.SPEED_PLAYER
    assert s1.world.laws
    assert s1.turn == 0 and s1.pending is None
    assert set(s1.memory.keys()) == set(s1.scene.present)
    assert any(line.startswith("[Opening] ") for line in s1.public_log)


def test_author_merge_keeps_existing():
    """Author merge: empty field = unchanged; only what the user asked for changes, everything else is kept."""
    sc = Scenario(
        id="t",
        world=World(tone="wuxia", background="a frontier town", laws=["Law A"]),
        cards={"scar": CharCard(name="Scar", faction="enemy", abilities=["quick blade"], weaknesses=["afraid of fire"])},
    )
    # change world: only add a law; tone/background left empty → must not be wiped
    scen.apply_author_reply(sc, AuthorReply(reply="", block="world",
        world=World(tone="", background="", laws=["Law A", "Law B"])))
    assert sc.world.tone == "wuxia" and sc.world.background == "a frontier town"
    assert sc.world.laws == ["Law A", "Law B"]

    # change char: only weaknesses; abilities left empty → abilities must not be wiped
    scen.apply_author_reply(sc, AuthorReply(reply="", block="char", char_id="scar",
        char=CharCard(name="Scar", faction="enemy", weaknesses=["afraid of fire", "afraid of water"])))
    assert sc.cards["scar"].abilities == ["quick blade"]
    assert sc.cards["scar"].weaknesses == ["afraid of fire", "afraid of water"]

    # ledger: adding the player's state must not wipe the existing scar state (key-level merge)
    sc.ledger.characters["scar"] = CharLedger(posture="by the door")
    scen.apply_author_reply(sc, AuthorReply(reply="", block="ledger",
        ledger=Ledger(characters={"player": CharLedger(posture="at the table")})))
    assert "scar" in sc.ledger.characters and "player" in sc.ledger.characters


def test_author_merge_preserves_directive():
    """When the author edits an existing character, the user-written directive isn't wiped (not in _CARD_FIELDS, so it's kept)."""
    sc = Scenario(id="t", cards={"scar": CharCard(name="Scar", faction="enemy", directive="Never surrender")})
    scen.apply_author_reply(sc, AuthorReply(reply="", block="char", char_id="scar",
        char=CharCard(name="Scar", faction="enemy", personality=["cunning"])))   # the AI didn't fill the directive (empty by default)
    assert sc.cards["scar"].directive == "Never surrender"   # directive kept, not wiped
    assert sc.cards["scar"].personality == ["cunning"]       # normal fields merge as usual


def test_author_new_character_drops_directive():
    """A brand-new character from the AI author never carries a directive (found in a live run: the model filled it like a goal)."""
    sc = Scenario(id="t")
    scen.apply_author_reply(sc, AuthorReply(reply="", block="char", char_id="ju",
        char=CharCard(name="Ju", faction="ally", motive="Protect Han", directive="Survive the night")))
    assert sc.cards["ju"].directive == ""
    assert sc.cards["ju"].motive == "Protect Han"
    assert "ju" in sc.scene.present


# ───────────────── incomplete scenarios: degrade (prune orphans) + game-start gate ─────────────────
def test_session_from_scenario_prunes_orphans():
    """present/ledger referencing non-existent character cards (orphans) → pruned at game start; ground_truth no longer KeyErrors."""
    sc = Scenario(
        id="orphans", scene=Scene(id="s", location="the ferry", present=["p1", "ghost_scene"]),
        cards={"p1": CharCard(name="Hero", faction="ally", controller="player")},
        ledger=Ledger(characters={"p1": CharLedger(), "ghost_ledger": CharLedger()}),
    )
    s = scen.session_from_scenario(sc)
    assert s.scene.present == ["p1"]                       # orphan present id pruned
    assert set(s.ledger.characters) == {"p1"}              # orphan ledger entry pruned
    assert "Hero" in engine.ground_truth(s)                # no crash (the old code KeyErrored here)


def test_prune_orphans_idempotent_and_on_load():
    """prune_orphans works directly on an existing Session (load path); a clean Session is unaffected."""
    s = new_tavern_session()
    before = (list(s.scene.present), set(s.ledger.characters))
    engine.prune_orphans(s)
    assert (list(s.scene.present), set(s.ledger.characters)) == before     # consistent scenario: unchanged
    s.ledger.characters["zombie"] = CharLedger()                        # inject an orphan
    s.scene.present.append("zombie")
    engine.prune_orphans(s)
    assert "zombie" not in s.ledger.characters and "zombie" not in s.scene.present


def test_validate_playable():
    """Game-start gate: a complete scenario gives None; missing player / player not present / nobody present each give a reason."""
    assert engine.validate_playable(new_tavern_session()) is None    # complete → playable

    def _sess(sc):
        return scen.session_from_scenario(sc)

    # no player (all agents)
    no_player = _sess(Scenario(id="a", scene=Scene(id="s", present=["e1"]),
        cards={"e1": CharCard(name="Bandit", faction="enemy", controller="agent")}))
    assert "player" in engine.validate_playable(no_player)

    # player exists but isn't in present → no action bar, never gets a turn
    off_scene = _sess(Scenario(id="b", scene=Scene(id="s", present=["e1"]),
        cards={"p1": CharCard(name="Hero", faction="ally", controller="player"),
                "e1": CharCard(name="Bandit", faction="enemy", controller="agent")}))
    assert "not present" in engine.validate_playable(off_scene)

    # nobody present
    empty = _sess(Scenario(id="c", scene=Scene(id="s", present=[]), cards={}))
    assert engine.validate_playable(empty) is not None
