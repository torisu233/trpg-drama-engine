"""Prompt assembly for the character agents (pure logic, offline): world laws fed in + directive injection + reaction persona filled in.

Uses a "capturing fake LLM" — an offline LLMClient stand-in that records the prompt it receives for assertions (the llm is
an explicit parameter, so the fake is passed directly, no monkeypatch needed). Only tests "how the program builds the prompt",
not "whether the LLM obeys it" (that's for live runs).
"""
import asyncio
from backend import agents
from backend.models import Intent, Adjudication
from backend.scene import new_tavern_session


class CapturingLLM:
    """Fake LLM: offline; records the incoming prompt in last_prompt and returns a valid object."""
    def __init__(self):
        self.last_prompt = None

    async def call(self, prompt, schema, **kw):
        self.last_prompt = prompt
        if schema.__name__ == "Intent":
            return schema(action="Hold position and wait")
        if schema.__name__ == "Reaction":
            return schema(reaction="Brace and take the hit")
        if schema.__name__ == "Narration":
            return schema(public="(placeholder narration)")
        return schema()

    async def close(self):
        pass


def _intent_prompt(s, cid):
    cap = CapturingLLM()
    asyncio.run(agents.character_intent(cap, s, cid))
    return cap.last_prompt


def _reaction_prompt(s, cid, incoming="The player lunges with his sword"):
    cap = CapturingLLM()
    asyncio.run(agents.character_reaction(cap, s, cid, incoming))
    return cap.last_prompt


def _adjudicate_prompt(s, intent=None):
    cap = CapturingLLM()
    intent = intent or Intent(actor="scar", action="Hold position and wait")
    asyncio.run(agents.adjudicate(cap, s, intent, None, None))
    return cap.last_prompt


def _narrate_prompt(s, adj=None, intent=None):
    cap = CapturingLLM()
    adj = adj or Adjudication()
    intent = intent or Intent(actor="scar", action="Hold position and wait")
    asyncio.run(agents.narrate(cap, s, adj, intent, None))
    return cap.last_prompt


def test_intent_prompt_includes_world_laws():
    """The character intent prompt includes the world laws (all laws are fed to characters)."""
    s = new_tavern_session()
    p = _intent_prompt(s, "scar")
    assert "# World Laws" in p
    assert "shield themselves with inner energy" in p          # the content of laws[0] really is fed in


def test_intent_prompt_injects_directive_when_set():
    """With a directive set → the prompt contains the high-priority directive block + the directive text."""
    s = new_tavern_session()
    s.cards["scar"].directive = "You never reveal to the player who is really behind this"
    p = _intent_prompt(s, "scar")
    assert "# ★ DIRECTIVE" in p                                                    # directive block injected
    assert "You never reveal to the player who is really behind this" in p        # directive text


def test_intent_prompt_no_directive_block_when_empty():
    """No directive set (empty by default) → no directive block."""
    s = new_tavern_session()                         # scar.directive defaults to ""
    p = _intent_prompt(s, "scar")
    assert "# ★ DIRECTIVE" not in p                  # empty → no block


def test_intent_rules_reassert_over_directive():
    """The rules section states it "cannot be overridden by any persona or Directive" — the directive only overrides the persona, never the rules."""
    s = new_tavern_session()
    p = _intent_prompt(s, "scar")
    assert "cannot be overridden by any persona or Directive" in p


def test_reaction_prompt_adds_laws_motive_identity_and_directive():
    """Reaction prompt: world laws + motive + backstory filled in, and the directive is injected too."""
    s = new_tavern_session()
    scar = s.cards["scar"]
    scar.directive = "You only speak in three-word sentences"
    p = _reaction_prompt(s, "scar")
    assert "# World Laws" in p and "shield themselves with inner energy" in p   # laws
    assert scar.motive in p                         # motive filled in
    assert scar.backstory in p                      # backstory filled in
    assert "# ★ DIRECTIVE" in p and "You only speak in three-word sentences" in p  # directive injected


def test_prompts_require_english_output():
    """Every agent prompt asks the model to write its output in English."""
    s = new_tavern_session()
    assert "Write everything in English." in _intent_prompt(s, "scar")
    assert "Write everything in English." in _reaction_prompt(s, "scar")
    assert "Write all text values in English." in _adjudicate_prompt(s)
    assert "Write all narration in English." in _narrate_prompt(s)


def test_adjudicate_prompt_enum_values_match_engine():
    """The enum values the adjudicator is told to output are exactly the ones the engine compares against."""
    p = _adjudicate_prompt(new_tavern_session())
    assert '"feasibility": "impossible/hindered/feasible/needs_rewrite"' in p
    assert '"outcome": "success/success_with_cost/reversal"' in p
    assert "bad_luck" in p and "good_luck" in p and "even" in p
    assert "ally/enemy/neutral" in p
    assert '"subject":"character name or scene"' in p


# ───────────────── non-stereotyped/time_skip: scene bounds on the intent side + anti-repetition + concrete new moves ─────────────────
def test_intent_prompt_has_scene_bound_and_anti_repeat():
    """Intent prompt: awareness of scene bounds + compressed exits + escalated anti-repetition + proactive concrete new moves."""
    p = _intent_prompt(new_tavern_session(), "scar")
    assert "single, bounded scene" in p                                   # scene-bound awareness
    assert "compress it into one line" in p and "quickly bought it and came back" in p   # compressed exit (one line, no real exit)
    assert "must be substantively different" in p                         # escalated anti-repetition
    assert "concrete new move that is visible on the spot" in p           # quiet scenes: proactive concrete new move


# ───────────────── time_skip: broader adjudication menu + time-jump output ─────────────────
def test_adjudicate_prompt_has_nonfight_levers_and_advance_field():
    """Adjudication prompt: anti-stalemate menu includes non-combat levers + compressed exits/time jumps + output has a "time_skip" field."""
    p = _adjudicate_prompt(new_tavern_session())
    assert "combat and non-combat options side by side" in p          # mixed menu, no hard branch
    assert "concrete, visible change" in p                             # non-combat lever
    assert "Compressed exits" in p and "time jump" in p                # compressed exit / skipping dead time
    assert '"time_skip"' in p                                          # output JSON has the time_skip key


# ───────────────── time_skip + anti-recycling: narration side ─────────────────
def test_narrate_prompt_anchor_downgrade_and_no_recycle():
    """Narration prompt: anchors downgraded (no need to restate every beat) + don't recycle environment/signature traits."""
    p = _narrate_prompt(new_tavern_session())
    assert "no need to restate every beat" in p                        # anchors downgraded from "must recite" to "reference"
    assert "Don't recycle the environment or signature traits" in p    # no recycled atmosphere/signature expressions
    assert "never copy it verbatim or wholesale" in p                  # anti-echo: even low-novelty beats don't copy earlier text


def test_narrate_prompt_injects_timeskip_when_set():
    """Adjudication filled in time_skip → the narration prompt has the time-jump block + the compression text; otherwise none."""
    s = new_tavern_session()
    with_jump = _narrate_prompt(s, Adjudication(time_skip="Half an hour later Chloe comes back carrying ice cream"))
    assert "⏭ Time Jump" in with_jump and "Half an hour later Chloe comes back carrying ice cream" in with_jump
    no_jump = _narrate_prompt(s, Adjudication())           # time_skip defaults to empty
    assert "⏭ Time Jump" not in no_jump                     # empty → no jump block
