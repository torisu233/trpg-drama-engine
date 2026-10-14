"""Boundary contract tests: drive a real, complete beat with a "hostile but valid" fake LLM to guard the LLM↔engine seam.

Why this layer exists (see earlier production incidents):
The other tests **never actually call the LLM** (see the conftest note), so the whole class of bugs where "what the LLM emits
differs from what the program assumes" is structurally invisible to the suite — they all live on the boundary between
free-form LLM output and rigid program assumptions:
  · KeyError 'Kyle': the LLM used a **character name** as a perception-map key while the code indexed s.cards[name] directly → crash.
  · self:name visibility: the LLM wrote self:<name>, the code assumed self:<id> → self-only states stopped working.
  · Made-up keys: the LLM invented a non-existent character name as a key → crash.
  · player id != "player": identifying the player by a hard-coded id → wrong character / hang.

Rather than calling helpers, this file plugs a `FakeLLM` (schema-valid, but **always keyed by character name**, with self:name
and **made-up keys**) into `flow` and runs a full beat (intent → reaction → adjudication → apply → narration → distribute → log), asserting:
  (1) no crash, no hang; (2) name-keyed delta/speed/faction/perception/private narration all land on the right character;
  (3) self:name is normalized to self:id; (4) made-up keys are silently skipped.
The fixture is deliberately **not tavern-shaped**: player id != "player" and character ids != names, forcing the name↔id distinction.

Against the old (pre-fix) code this test crashes (KeyError) — exactly the regression value it should have.
"""
import asyncio

from backend import flow, engine, config
from backend.models import (
    Session, Scene, CharCard, Ledger, CharLedger,
    Intent, Reaction, Adjudication, LedgerDelta, DeltaItem, Narration,
    Summary, ConsolidateOut,
)


# ───────────────── hostile fake LLM ─────────────────
class FakeLLM:
    """Stands in for LLMClient: returns **valid but hostile** output per schema (keys are all character names + self:name + made-up keys).

    Mimics DeepSeek's real tendency to use character names rather than abstract ids as keys everywhere. Never touches the network.
    """
    async def call(self, prompt, schema, temperature=0.7, max_tokens=2000, model=""):
        name = schema.__name__
        if name == "Intent":
            # the enemy Man in Black closes in on teammate "Ah Da" — target given by **name**; the engine must resolve it to an id at the boundary
            return Intent(action="Closes in on Ah Da, blade flashing straight at his wrist", target="Ah Da", covert=False)
        if name == "Reaction":
            return Reaction(reaction="Raises the oar crosswise to block in front of his chest")
        if name == "Adjudication":
            # every character-keyed field uses **names**, plus a **made-up key** and a self:name visibility
            return Adjudication(
                feasibility="feasible", outcome="success_with_cost",
                relevant_conditions=["Man in Black's quick blade", "Ah Da blocks with the oar"],
                rulings=["quick blade activates", "the block is rewritten as taking a hit"],
                ledger_delta=LedgerDelta(add=[
                    DeltaItem(subject="Ah Da", category="conditions", content="cut on the right arm",
                              gates="can't put full strength into it", visibility="self:Ah Da"),   # self:name → must normalize to self:id
                ]),
                speed_updates={"Ah Da": 3},                    # name key
                perception_updates={"Ah Da": "distracted by pain"},  # name key
                faction_changes={"Man in Black": "neutral"},    # name-keyed defection
                perception_map={"Lin Wudi": "all", "Nobody": "none",   # ← made-up key; the old code KeyErrored here
                                "Ah Da": "partial", "Man in Black": "all"},
                gm_summary="The Man in Black cuts Ah Da's arm; Ah Da barely blocks.",
            )
        if name == "Narration":
            return Narration(
                public="The ferry landing is cold and damp. The Man in Black darts in with a slash; Ah Da braces the oar to block, sparks fly, and blood already marks his wrist.",
                private={"Ah Da": "Ah Da feels his right arm go numb; his grip on the oar weakens.",   # name key
                         "Ghost": "a private view for a character who doesn't exist"},          # ← made-up key; distribute must skip it
            )
        if name == "Summary":
            return Summary(summary="(test summary)")
        if name == "ConsolidateOut":
            return ConsolidateOut(conditions=[])
        raise AssertionError(f"FakeLLM got an unexpected schema: {name}")

    async def close(self):
        pass


# ───────────────── non-tavern fixture: player id != "player", ids != names ─────────────────
def _hostile_session() -> Session:
    """Three characters, deliberately shaped unlike the tavern to force the name↔id distinction.

    Gauges are set carefully (threshold 20 / player speed 7 / normal speed 5): on the first tick only h3 reaches the threshold →
    the enemy takes one full beat; then h1 (player) reaches it → advance stops exactly at the player's decision point.
    So advance runs exactly "one enemy beat".
    """
    cards = {
        "h1": CharCard(name="Lin Wudi", faction="ally", controller="player", gender="male",
                       backstory="a down-and-out swordsman", abilities=["precise swordsmanship"], weaknesses=["old wound in the left shoulder"]),
        "h2": CharCard(name="Ah Da", faction="ally", controller="agent", gender="male",
                       abilities=["very strong"], weaknesses=["simple-minded"]),
        "h3": CharCard(name="Man in Black", faction="enemy", controller="agent", gender="male",
                       abilities=["Canal Gang quick blade"], defenses=["iron-body protection"], weaknesses=["afraid of water"]),
    }
    ledger = Ledger(characters={
        "h1": CharLedger(posture="standing at the bow", speed=config.SPEED_PLAYER, gauge=6),
        "h2": CharLedger(posture="at his side holding an oar", speed=config.SPEED_NORMAL, gauge=0),
        "h3": CharLedger(posture="striding across the waves", speed=config.SPEED_NORMAL, gauge=15),
    })
    return Session(
        scene=Scene(id="hs", location="a ferry landing in the night fog", present=["h1", "h2", "h3"]),
        cards=cards, ledger=ledger,
        memory={"h1": [], "h2": [], "h3": []},
        public_log=["[Scene] a ferry landing in the night fog"],
    )


def _run(coro):
    return asyncio.run(coro)


# ───────────────── contract: a full beat survives hostile output ─────────────────
def test_npc_beat_survives_name_keyed_and_fictional_llm_output():
    """A full enemy beat: intent/reaction/adjudication/narration all keyed by character name, with self:name and made-up keys →
    no crash, no hang; every name key lands on the right character, self:name is normalized, made-up keys are skipped."""
    s = _hostile_session()

    # the player is identified by controller=="player", never a hard-coded "player"
    assert engine.player_id(s) == "h1"

    # run to the player's decision point (by the gauge setup, exactly one enemy beat) — no exception proves the boundary held
    _run(flow.advance(FakeLLM(), s))

    # stopped at the player's action, no hang
    assert s.pending and s.pending["type"] == "player_action"

    h2 = s.ledger.characters["h2"]
    # name-keyed ledger_delta (subject="Ah Da") landed on h2
    assert any("cut on the right arm" in c.content for c in h2.conditions), "name-keyed delta did not land on the right character"
    # self:name → self:id normalization (before the fix it stayed self:Ah Da and self-visibility never matched)
    wound = next(c for c in h2.conditions if "cut on the right arm" in c.content)
    assert wound.visibility == "self:h2", f"self:name was not normalized to self:id: {wound.visibility}"
    assert engine._visible(wound, "h2", "ally") is True      # visible to self
    assert engine._visible(wound, "h1", "ally") is False     # invisible to others

    # name-keyed speed_updates / perception_updates landed on h2
    assert h2.speed == 3, "name-keyed speed_updates had no effect"
    assert "distracted by pain" in h2.perception, "name-keyed perception_updates had no effect"

    # name-keyed faction_changes (Man in Black → neutral) landed on h3
    assert s.cards["h3"].faction == "neutral", "name-keyed faction_changes had no effect"

    # private narration: name key "Ah Da" delivered to h2; made-up key "Ghost" skipped without crashing
    assert s.memory["h2"][-1] == "Ah Da feels his right arm go numb; his grip on the oar weakens.", "name-keyed private narration not delivered"
    assert "arm go numb" not in s.memory["h1"][-1]               # the player gets the public version, not someone else's private one
    assert "blood already marks his wrist" in s.memory["h1"][-1]  # public narration enters the player's memory


def test_player_beat_survives_name_keyed_llm_output():
    """A player-initiated beat (target given by the enemy's **name**): intent → reaction → adjudication → narration runs end to end and records state, no crash."""
    s = _hostile_session()
    pid = engine.player_id(s)
    assert pid == "h1"

    # the player thrusts at "Man in Black" (by name); the engine resolves it to h3 at the boundary and collects his reaction
    action = {"action": "Thrusts his sword straight at the Man in Black's throat", "target": "Man in Black", "covert": False}

    async def drive():
        async for _ in flow._player_action_beat(FakeLLM(), s, action):
            pass

    _run(drive())   # no exception = boundary held

    # the beat was recorded: name-keyed delta/speed/faction/private all took effect (same source as above, reusing the key assertions)
    h2 = s.ledger.characters["h2"]
    assert any("cut on the right arm" in c.content for c in h2.conditions)
    assert h2.speed == 3
    assert s.cards["h3"].faction == "neutral"
    # the structured log recorded this beat, and the player's action text is visible (ally)
    last = s.log[-1]
    assert last["actor"] == "h1" and last["controller"] == "player"
    assert last["action_text"] == "Thrusts his sword straight at the Man in Black's throat"


class HiddenFakeLLM(FakeLLM):
    """An enemy **covert** beat that gets away with it: adjudication returns detected=False + cover (the disguised visible action)."""
    async def call(self, prompt, schema, temperature=0.7, max_tokens=2000, model=""):
        name = schema.__name__
        if name == "Intent":
            # the enemy ambushes teammate "Ah Da" (an NPC), covert — the true intent must not reach the player-visible layer
            return Intent(action="Slips behind Ah Da while no one is looking, ready to strike him down", target="Ah Da", covert=True)
        adj = await super().call(prompt, schema, temperature, max_tokens, model)
        if name == "Adjudication":
            adj.detected = False
            adj.cover = "just leans in to chat with Ah Da"
        return adj


def test_hidden_enemy_beat_shows_surface_not_true_intent():
    """An enemy covert action gets away with it: after adjudication the structured log's action_text = cover; the true intent never leaks to the player."""
    s = _hostile_session()
    _run(flow.advance(HiddenFakeLLM(), s))   # run the enemy beat, stop at the player

    foe_beats = [e for e in s.log if e.get("actor") == "h3"]
    assert foe_beats, "the enemy covert beat was not recorded in the structured log"
    last = foe_beats[-1]
    assert last["action_text"] == "just leans in to chat with Ah Da"      # shows the cover
    assert "strike him down" not in (last["action_text"] or "")           # the true intent never appears in the player-visible chip


def test_target_resolves_player_by_role_not_hardcoded_id():
    """Resolving an enemy intent's target: the player is found by controller and characters by name, never by hard-coded ids."""
    s = _hostile_session()
    # the enemy targets the player by **name** "Lin Wudi" → must resolve to h1 and be judged "collect a reaction from the player"
    intent = Intent(actor="h3", action="Spins around and lunges at Lin Wudi", target="Lin Wudi")
    assert engine.target_char(s, intent) == "h1"
    assert engine.needs_reaction(s, intent) == "h1"     # always collect a reaction from the player (h1 recognized by controller)
