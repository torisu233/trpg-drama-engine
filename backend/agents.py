"""Wrappers for the four agents (adjudication / narration / character intent / character reaction).

Responsibilities, per section 11 of the design doc:
- character agent: sees only its visible view + its own card; outputs intents/reactions and never declares success or failure
- adjudication agent: action ruling + knowledge ruling (dual output); obeys the world laws and character traits, with the ground truth as its only source
- GM/narration agent: writes prose per recipient according to the perception map, matches the world tone, invents no new entities
"""
from typing import Optional
from .llm_client import LLMClient
from .models import (
    Session, Intent, Reaction, Adjudication, Narration, Summary,
    Condition, ConsolidateOut, Scenario, AuthorReply,
)
from . import engine, config


def _roster(s: Session) -> str:
    """Roster of present characters (**referred to by name**; includes gender so nobody guesses)."""
    return ", ".join(
        s.cards[cid].name + (f" ({s.cards[cid].gender})" if s.cards[cid].gender else "")
        for cid in s.scene.present if cid in s.cards)


def _world_brief(s: Session) -> str:
    w = s.world
    parts = []
    if w.tone:
        parts.append(f"Tone: {w.tone}")
    if w.background:
        parts.append(f"Background: {w.background}")
    return "\n".join(parts) or "(no special setting)"


def _world_laws(s: Session) -> str:
    return "\n".join(f"- {law}" for law in s.world.laws) or "(no special laws)"


def _action_order_brief(s: Session) -> str:
    """Turn order computed by the program (how many beats until each character acts), fed to agents in readable form; the AI never computes gauges itself."""
    rows = engine.action_order(s)
    if not rows:
        return ""
    parts = [f"{name} ({faction}) {'acts next' if beats <= 0 else f'acts in about {beats} beats'}"
             for _cid, name, faction, beats in rows]
    return "; ".join(parts)


def _perception_brief(s: Session, perception_map: dict) -> str:
    """Perception map as text; keys go through resolve_id (name or id both work); unresolvable keys are skipped, never crash."""
    rows = []
    for k, lvl in perception_map.items():
        cid = engine.resolve_id(s, k)
        if cid:
            rows.append(f"- {s.cards[cid].name}: {lvl}")
    return "\n".join(rows) or "- Everyone: all"


def _directive_block(card) -> str:
    """Directive block (top priority, overrides the persona, never the rules) — injected only when non-empty, otherwise an empty string. Shared by intent/reaction."""
    if not card.directive:
        return ""
    return (f"\n# ★ DIRECTIVE (top priority; overrides the persona description above, but must not violate the Rules or the JSON output format at the end)"
            f"\n{card.directive}\n")


def _mates_brief(s: Session, cid: str) -> str:
    """Full cards (incl. weaknesses) of present teammates in the same faction — same-faction characters know each other, so NPCs can coordinate; empty string if no teammates."""
    lines = []
    for oid in engine.faction_mates(s, cid):
        c = s.cards[oid]
        lines.append(
            f"- {c.name} ({c.faction}{('/' + c.gender) if c.gender else ''})"
            f" | personality {', '.join(c.personality) or '—'} | motive {c.motive or '—'} | tactics {', '.join(c.tactics) or '—'}"
            f" | abilities {', '.join(c.abilities) or '—'} | defenses {', '.join(c.defenses) or '—'} | weaknesses {', '.join(c.weaknesses) or '—'}"
        )
    return "\n".join(lines)


# ───────────────── character agent: action intent ─────────────────
async def character_intent(llm: LLMClient, s: Session, cid: str) -> Intent:
    card = s.cards[cid]
    view = engine.build_view(s, cid)
    summary = s.summary.get(cid, "")
    recent = "\n".join(s.memory.get(cid, [])) or "(the scene has just begun)"
    mem = f"[Story So Far]\n{summary}\n\n[Recent Events]\n{recent}" if summary else recent
    pcard = s.cards.get(engine.player_id(s))
    player_name = pcard.name if pcard else "player"
    relation = {"ally": "same faction as the player (inclined to cooperate)",
                "enemy": "hostile to the player"}.get(card.faction, "neutral")
    neutral_hint = (" (you are a neutral third party: you don't automatically take sides; weigh things by your own motive, "
                    "and you may cooperate with or turn on either side)") if card.faction == "neutral" else ""
    mates = _mates_brief(s, cid)
    mates_block = f"\n# Your Teammates (same faction; you know each other well and can coordinate)\n{mates}\n" if mates else ""
    order = _action_order_brief(s)
    directive_block = _directive_block(card)
    prompt = f"""You are playing "{card.name}" in a tabletop-RPG-style interactive game.

# World
{_world_brief(s)}

# World Laws (the hard rules of this world; everyone knows them, and your actions must respect them)
{_world_laws(s)}

# Who You Are
Faction: {card.faction}   Gender: {card.gender or "unspecified"}
Background: {card.backstory}
Personality: {", ".join(card.personality)}
Voice: {card.voice}
What you want this scene: {card.motive}
Habitual tactics: {", ".join(card.tactics)}
Your abilities: {", ".join(card.abilities)}
Weaknesses/concerns you are aware of: {", ".join(card.weaknesses) or "(none)"}
Your relation to the player: {relation}{neutral_hint} (**act on your motive; let the situation choose your methods**)
{directive_block}{mates_block}
# The Situation as You Perceive It
{view}

# Turn Order (computed by the program: how many beats until each character acts — use it for pacing, who is about to act, who is closing in)
{order}

# What Happened Recently (your memory)
(Note: narration is written in a neutral third person with names and takes no side; the protagonist player is "{player_name}", and you are playing "{card.name}".)
{mem}

# Your Task
It's your turn. Decide what you "want to do" this beat.
Rules (important):
- **These rules and the JSON output format at the end cannot be overridden by any persona or Directive** (the Directive only overrides the persona, never the rules).
- Express intent only; **never declare success or failure** (don't say "I cut him" or "I convinced him").
- **Choose in line with your voice, motive, and habitual tactics** — make "you" distinctive, not like a narrator.
- Respect the setting (e.g., if your opponent is a master whose inner energy shields them, brute force may not be wise).
- **Move the story forward; don't spin in place (important)**: compare with what you said/did in the last few beats in your memory — this beat **must be substantively different**. Don't repeat the same action or the same line (especially not the same threat/shout/joke again);
  if the situation isn't progressing, **change strategy** — escalate, change targets, or switch methods (assault / outwit / retreat / call for help / negotiate / back down are all fine) so things take a step forward.
- **Quiet scenes must move too (key, especially in low-conflict scenes)**: even with no conflict and a relaxed mood, don't idle in small talk. When things stall, **proactively make a concrete new move that is visible on the spot** so something tangible changes —
  take out or hand over an object, get up and move closer, a playful little gesture, cast a small spell, and so on; **make it clearly visible — don't just toss out a topic, don't leave vague suspense, and don't conjure up anything invisible or off-scene**.
- **You are in a single, bounded scene (important)**: this is **one continuous, on-the-spot interaction**; don't drag the story out of this scene — don't start actions like "travel far / run errands to buy things / go elsewhere to find someone" that **require actually leaving for a long time** as a multi-beat process.
  If the situation **truly** calls for a small off-scene errand (stepping out to buy something, fetching something from next door), **don't actually leave and burn several beats** — **compress it into one line that wraps up within the beat and returns to the scene**, like "I quickly bought it and came back" or "I turn and fetch the book".
- **Methods fit the situation**: this isn't necessarily a fight — negotiate when it's time to negotiate, deceive or disguise when it's time to deceive, get close or show goodwill when it's time to, and fight only when it's time to fight; pick what best suits your motive and the current situation, don't mindlessly start a brawl.
- If you are badly wounded or at a disadvantage, you may act conservatively or even give up (set action to "Hold position and wait").
- To act covertly (a meaningful glance, a secret signal), set "covert" to true.
- **One beat = one action (key)**: write **one short sentence (about 25 words at most)** — a single main move, including how you do it. If you speak, give **one short line (about 12 words at most)** in your own voice. You may add one tiny side gesture (e.g., a wink while talking), nothing more: don't chain several moves, don't narrate your feelings or the room. Put the main target in "target".
- **You may defect or switch sides on your own (rarely, and with a reason)**: if the story leads you to change factions (persuaded, driven by interest, a debt of gratitude, surrendering while you still can…), set "faction_switch" to the target faction (ally/enemy/neutral) and act out the change in "action". This is only a **proposal**; adjudication decides whether it takes effect (joining the ally side especially needs good enough reason to be accepted). Otherwise set it to null.
- Write everything in English.

Output JSON only:
{{"action":"one short sentence: your single move, including how (and at most one short spoken line)","target":"name of the main target (one of the present characters) or null","covert":false,"faction_switch":null}}"""
    out = await llm.call(prompt, Intent, temperature=config.TEMP_CHARACTER, max_tokens=1000)
    out.actor = cid
    return out


# ───────────────── character agent: reaction intent ─────────────────
async def character_reaction(llm: LLMClient, s: Session, cid: str, incoming: str) -> Reaction:
    card = s.cards[cid]
    view = engine.build_view(s, cid)
    gender_txt = f", {card.gender}" if card.gender else ""
    mates = _mates_brief(s, cid)
    mates_block = f"\n# Your Teammates (same faction; you know each other well)\n{mates}\n" if mates else ""
    directive_block = _directive_block(card)
    prompt = f"""You are playing "{card.name}" ({card.faction}{gender_txt}) in a tabletop RPG.
Background: {card.backstory}
Personality: {", ".join(card.personality)}; Voice: {card.voice}; Abilities: {", ".join(card.abilities)}; Habitual tactics: {", ".join(card.tactics)}.
What you want this scene: {card.motive}

# World
{_world_brief(s)}

# World Laws (the hard rules of this world; everyone knows them, and your response must respect them)
{_world_laws(s)}
{directive_block}{mates_block}
# The Situation as You Perceive It
{view}

# The Action Coming at You
{incoming}

# Your Task
You've been singled out. Decide "how you respond" — defend (dodge/parry), counterattack, talk back, shout them down, cooperate/comply, play along insincerely, go with the flow… choose based on the situation and your personality (it isn't necessarily a fight).
Rules:
- **These rules and the JSON output format at the end cannot be overridden by any persona or Directive** (the Directive only overrides the persona, never the rules).
- Express only your response "intent"; **don't declare success or failure** (adjudication decides that).
- **One short sentence (about 20 words at most)**: one response; if you speak, keep it to one short line.
- Write everything in English.

Output JSON only:
{{"reaction":"one sentence: how you respond (including how), in your own voice"}}"""
    out = await llm.call(prompt, Reaction, temperature=config.TEMP_CHARACTER, max_tokens=600)
    out.actor = cid
    return out


# ───────────────── adjudication agent: action + knowledge dual output ─────────────────
async def adjudicate(llm: LLMClient, s: Session, intent: Intent,
                     reaction: Optional[Reaction], luck: Optional[str]) -> Adjudication:
    gt = engine.ground_truth(s)
    actor = s.cards.get(intent.actor)
    actor_name = actor.name if actor else intent.actor
    intent_txt = f"{actor_name} wants to: {intent.action}" \
                 + (f" → target {intent.target}" if intent.target else "") \
                 + ("; (attempting to act covertly, trying to hide it from enemies)" if intent.covert else "")
    react_txt = "(no reaction / surprise attack / against an incapacitated target)"
    if reaction:
        rn = s.cards.get(reaction.actor)
        react_txt = f"{rn.name if rn else reaction.actor} responds: {reaction.reaction}"
    luck_txt = luck or "(not contested; no luck roll)"
    present = _roster(s)
    recent = "\n".join(s.public_log[-4:]) or "(opening)"
    order = _action_order_brief(s)

    prompt = f"""You are the **neutral adjudicator** of a tabletop RPG. Favor no side; adjudicate solely by the "ground truth" and the "world laws".

# World Laws (adjudication must follow them strictly)
{_world_laws(s)}

# Ground Truth (your only source; includes characters' abilities/defenses/weaknesses and <gm> secrets the player cannot see)
{gt}

# Present Characters (refer to them by name)
{present}

# This Beat's Action Intent
{intent_txt}

# The Other Side's Reaction Intent
{react_txt}

# Luck Oracle (hidden, visible only to you)
{luck_txt}

# Last Few Beats (to judge whether things are repeating in place and need to move forward; this is beat {s.turn})
{recent}

# Turn Order (computed by the program: how many beats until each character acts — a reference for pacing and for when approaching events like "reinforcements / pursuers / spreading fire" arrive)
{order}

# Adjudication Principles
- **Strictly obey the world laws and character traits**: against someone with "defenses" (e.g. impervious to blades / iron-body training), ordinary blades and fists are useless or heavily reduced;
  only the routes the laws list (stronger inner energy, poison, fire, pressure points, a surprise strike at their weakness, cutting off their foundation) work. Hitting an opponent's "weaknesses" has a marked effect.
- The ground truth is your only source. Characters cannot declare their own success or failure; if the intent contradicts the state or the laws, rule it impossible or hindered.
- **Rarely give a clean success**; most outcomes are "success_with_cost" — that cost is the fuel that keeps the scene rolling.
- **No stalemates; move the story forward (important, applies to every mode)**: if the last few beats repeat in place (the same action/dialogue loop, nobody actually advancing), make the situation **change qualitatively** this beat — don't give another "tug of war, nothing moves" result.
  Pick the **most fitting** lever for this scene from below (combat and non-combat options side by side — use whichever fits; don't default to combat or threats):
  · **There is a queued threat/crisis** → let the threat planted at the start **come due** over time (if the ground truth says "reinforcements arrive within a few exchanges", have them arrive), escalate an environmental crisis to force a choice (fire out of control, escape route about to be cut off, time running out), or make someone who keeps failing pay a real cost and lose options;
  · **No threat to cash in; just a stall in a quiet/everyday scene or a lull in negotiation** → bring about a **concrete, visible change** (someone makes a new move, a relationship takes a step, a new object or situation appears), or use a **time jump** to skip dead time (see "time_skip" below) — **don't force a fight or conjure up a threat out of nowhere**.
- **Time is flowing**: things in the ground truth that are "about to arrive / closing in" cannot be stalled forever; they should come due as beats pass. When there is nothing pending like that, use the non-combat levers above to push the scene into a new phase just the same.
- **Compressed exits / time jumps (fill the "time_skip" field, important)**: when an action intent is essentially a **small off-scene errand** ("I'll be right back with it", "stepping out to fetch something", "waiting for him for half an hour"), or the scene is stuck in a stall that **can only move by skipping dead time**,
  **don't let the character actually leave and burn several beats** — resolve it on the spot this beat: record the action's result in the ledger as usual (e.g. a social fact "the ice cream has been bought"), and write a one-line **time-compression description** in "time_skip" (e.g. "Half an hour later Chloe comes back carrying ice cream"); characters **always stay in the scene**. Otherwise "time_skip" must be left empty.
- Consequences should be "qualitative and change capabilities": write "stabbed in the right arm, can only use the left hand", not numbers.
- **Interaction isn't limited to combat; the same adjudication applies to every mode** — use the qualitative consequences that fit the mode, don't force injuries:
  · Dialogue/negotiation → trust/suspicion/wavering/concessions/leverage/promises (mostly recorded as social facts)
  · Disguise/infiltration → whether they are seen through or arouse suspicion, whether the cover holds, identity clues revealed (use covert and the perception map)
- Luck: bad_luck → drop one tier or add an unlucky complication; good_luck → allow a rare clean success or a favorable turn; even → as normal.
- **Covert actions (important; mandatory when this beat's action is marked "attempting to act covertly")**: first decide **whether it is seen through** — considering the opponents' perception/alertness, luck, and the difficulty of the action.
  · Seen through → set `detected` to true and leave `cover` empty (the truth is exposed; narrate the true intent, and record the exposure in the ledger and perception map as needed).
  · Gets away with it → set `detected` to false and write in `cover` one line describing **the innocent-looking visible action bystanders will believe** (different from the true intent, seemingly harmless or reasonable; e.g. true intent "wink to pass a secret signal" → cover "raises his cup and takes a sip"). Only their own faction understands the true intent (use visibility/perception_map).
  · Non-covert action: `detected`=false and `cover` empty.
- **Compound actions**: a beat may contain "one main action + a small side action" (e.g. attacking while signaling, backing off while taunting). **Rule on each part**,
  and weigh the cost of "doing two things at once" — usually the main action is weakened, or the side action doesn't fully land (great material for "success_with_cost").
  "target" is only the main reacting party; side targets (e.g. a teammate receiving a signal) are handled by you in the perception map, no separate reaction needed.
- **Record social/information consequences in the ledger**: if dialogue, negotiation, or coercion produces a lasting result (a confession, promise, truce, alliance, revealed intel),
  record it in ledger_delta as a social fact (subject "scene", category "social_facts" or "intel"), with gates and visibility.
- **Give transient states an expiry**: for short-lived states like swaying posture / being startled / spreading firelight / momentary loss of balance, set "ttl" (1-3, disappears automatically after a few beats) when adding;
  for persistent states like injuries / poison / promises / emotional shifts / social facts, leave it null (omit it).
- **Escalation replaces the old entry; never stack near-duplicate states**: when a state worsens or is superseded (the fire grows, a wound worsens, fear escalates, posture changes),
  **first put the old version's keyword in remove, then write the new version in add** — never let the ledger hold several near-duplicate entries describing the same thing.
  remove keywords must be **long enough to uniquely identify** the old entry (not a generic word like "fear", which would delete other entries; use a distinctive fragment like "fear intensifying, may break and confess").
- **Record each fact in one place only**: a confession/promise/intel goes in "social_facts"; **don't also copy it into a character's conditions**.
- Visibility must be exactly one of these four: `public` / `gm` / `faction:<faction>` / `self:<character name>` (don't invent other values).
- perception_map: decide "who noticed this, and how much". Unconscious characters notice nothing; a badly wounded, distracted character may miss it; something behind someone's back may go unnoticed.
- **Character-keyed fields (perception_map/speed_updates/perception_updates/faction_changes) and "subject" must always use the character names from "Present Characters" above (the program maps them automatically).**
- **faction_changes (defecting/joining/being turned/surrendering)**: if a character proposes switching factions (see "faction_switch" in the action intent) or the story makes them change sides, approve it only **with enough narrative grounds**, by writing it into "faction_changes" (character name → new faction ally/enemy/neutral); **the bar for joining "ally" is high** (they must be persuaded / owe a debt of gratitude / have enough to gain; it can't just be announced out of nowhere). If approved, point out the change in gm_summary so the narration explains it. Factions are only ally/enemy/neutral.
- Write all text values in English.

# Output (JSON only)
{{
 "relevant_conditions": ["states/traits/laws you checked that bear on this intent, one per item"],
 "rulings": ["each one → activates/blocks/rewrites/irrelevant, one sentence"],
 "feasibility": "impossible/hindered/feasible/needs_rewrite",
 "outcome": "success/success_with_cost/reversal",
 "ledger_delta": {{
    "add": [{{"subject":"character name or scene","category":"posture/conditions/status_effects/spatial/scene_facts/social_facts/intel","content":"qualitative fact","gates":"how it constrains what follows","visibility":"public","ttl":null}}],
    "remove": ["keyword of a state to remove"],
    "modify": []
 }},
 "speed_updates": {{"character name": integer speed (seriously wounded 3 / dying 2 / unconscious 0; omit if normal)}},
 "perception_updates": {{"character name": "e.g. blindfolded / unconscious / badly wounded and distracted"}},
 "faction_changes": {{"character name": "ally/enemy/neutral (only when approving a defection/joining/being turned; otherwise leave empty)"}},
 "perception_map": {{"character name": "all / partial:only saw the surface / none"}},
 "detected": false,
 "cover": "(only when this beat's action is covert and not seen through: the innocent-looking visible action bystanders believe; empty if seen through or not covert)",
 "time_skip": "(only for a compressed exit or when dead time must be skipped: a one-line time-compression description; characters don't leave and results are recorded separately; otherwise must be empty)",
 "gm_summary": "one sentence of ground truth for the narrator (what actually happened this beat, and the unresolved tension it ends on: a threat/doubt/choice)"
}}"""
    return await llm.call(prompt, Adjudication, temperature=config.TEMP_ADJUDICATOR, max_tokens=2500)


# ───────────────── GM / narration agent ─────────────────
def _vis_label(v: str) -> str:
    if v == "public":
        return "public"
    if v.startswith("faction"):
        return "known only to that faction"
    if v.startswith("self"):
        return "known only to that character"
    return "GM secret, must never appear in the public version"


async def narrate(llm: LLMClient, s: Session, adj: Adjudication, intent: Intent,
                  reaction: Optional[Reaction] = None) -> Narration:
    present = _roster(s)
    pcard = s.cards.get(engine.player_id(s))
    player_name = pcard.name if pcard else "player"
    order = _action_order_brief(s)
    perception = _perception_brief(s, adj.perception_map)

    actor = s.cards.get(intent.actor)
    actor_name = actor.name if actor else intent.actor
    covert_undetected = bool(intent.covert and adj.cover and not adj.detected)
    if covert_undetected:              # covert and not seen through: the public version may only use the cover; the true intent is for their faction's private versions only
        actor_line = f"{actor_name} appears to be: {adj.cover}" \
                     + (f" (target {intent.target})" if intent.target else "")
        covert_line = (f"\n# ⚠ True Intent (secret: may only be used in private versions for {actor_name}'s own faction; "
                       f"**must never appear in the public version** — the public version may only describe the visible action above)\n{actor_name} is actually: {intent.action}")
    else:                              # open, or covert but seen through: narrate the true intent
        actor_line = f"{actor_name} declares: {intent.action}" \
                     + (f" (target {intent.target})" if intent.target else "") \
                     + (" (attempted covertly; seen through/exposed)" if intent.covert else "")
        covert_line = ""
    reaction_line = ""
    if reaction:
        rn = s.cards.get(reaction.actor)
        reaction_line = f"\n# The Other Side's Response\n{rn.name if rn else reaction.actor}: {reaction.reaction}"
    changes = "\n".join(f"- {d.content} ({_vis_label(d.visibility)})" for d in adj.ledger_delta.add) \
        or "(no new states this beat)"
    recent_narr = "\n".join(s.public_log[-2:]) or "(opening)"
    anchors = "; ".join(c.content for c in (s.ledger.scene.spatial + s.ledger.scene.scene_facts)
                        if c.visibility == "public") or "(none)"
    ruling_material = ""
    if adj.relevant_conditions or adj.rulings:
        ruling_material = ("\n# Facts and Rulings Involved This Beat (you may describe them fully, but don't go beyond these facts)\n"
                           "Relevant conditions: " + "; ".join(adj.relevant_conditions) +
                           "\nRulings: " + "; ".join(adj.rulings))
    time_skip_block = (f"\n# ⏭ Time Jump (this beat compresses and skips dead time, important)\n{adj.time_skip}\n"
                       "(Compress the skipped stretch of time **into a single transitional line**, like \"Half an hour later…\"; don't narrate the skipped process beat by beat — land in the moment after the jump and continue from there. "
                       "The characters have not left; after the transition everyone is still in this same scene.)") if adj.time_skip else ""
    involved = [intent.actor] + ([reaction.actor] if reaction else [])
    voice_rows = []
    for cid in involved:
        c = s.cards.get(cid)
        if c:
            voice_rows.append(f"- {c.name}: personality {(', '.join(c.personality)) or '—'}; voice {c.voice or '—'}")
    voice_txt = ("\n# Personality and Voice of Those on Stage (keep dialogue and demeanor true to character)\n" + "\n".join(voice_rows)) if voice_rows else ""

    prompt = f"""You are the GM/narrator of a tabletop RPG. Write this beat as vivid prose in a **neutral third person**.

# World Tone (sets the writing style)
{s.world.tone or "(neutral)"}

# Present Characters (refer to them by name)
{present}

# Story So Far (what the player just saw; continue from it, but **never restate** events or dialogue already written)
{recent_narr}
(**The above is text already written, not a template to reuse**: even if this beat resembles the last one, **never copy it verbatim or wholesale** — write only what is new this beat, in fresh wording of your own.)

# Scene Anchors (only a **reference** for keeping the setting consistent — **no need to restate every beat**; unless this beat actually touches them, don't describe this existing environment/atmosphere again)
{anchors}

# Pacing (computed by the program: how many beats until each character acts)
{order}
(Purpose: sense "who is about to act, who is closing in" — if someone is still several beats away (e.g. reinforcements or pursuers on their way), you may build the atmosphere of their **gradual approach** (footsteps drawing near, hoofbeats growing louder, still outside the door); the closer they are, the tighter the writing. **But never put game numbers like "beats" into the narration**; use natural prose only.)

# This Beat's Actor
{actor_line}{covert_line}{reaction_line}
{voice_txt}

# This Beat's Ground Truth (you know everything)
{adj.gm_summary}
(outcome: {adj.outcome}; feasibility: {adj.feasibility})
{time_skip_block}

# State Changes Actually Caused This Beat (narrate faithfully from these; mind each one's visibility)
{changes}
{ruling_material}

# perception_map (who noticed how much — decides what each version may contain)
{perception}

# Narrative Perspective (most important, above everything): neutral third person, named, taking no side
- The public narration is **one objective account that holds true for everyone** — the player and every character agent read it and act on it. **Always use the third person and call characters by name** (including the player character "{player_name}"), **never "you"**, and never words that **shift with point of view** like "ally / enemy / friendly forces / we"; otherwise readers on different sides (especially NPC agents) will get the references backwards.
- **Describe by identity/affiliation (absolute), not by side (relative)**: write a person's name or what they belong to ("the Canal Gang thug", "the inn's waiter", "the Man in Black"), not "the enemy / reinforcements / friendly forces". When a relative relationship really must be stated, **attribute it explicitly to a named character** — write "the few Canal Gang men coming to back up Scar", not "reinforcements"; write "the man opposing Qing", not "the enemy".
- Private versions: add the unique perceptions of an NPC who "noticed more", written from that NPC's own perspective (likewise named, no "you").

# Narration Principles
- **Write only this beat's new developments (most important)**: continue from "Story So Far" above, but **don't restate events or dialogue already written**; don't have the same character say something similar again.
  If this beat is just "more stalling/standoff", write only the details **added** this beat (a glance, half a step, one new line), don't redescribe the whole scene.
- **Don't recycle the environment or signature traits (key)**: **don't recite the same batch of environment/atmosphere every beat** (sunlight, smells, distant sounds and other scene anchors) or **the same character's signature expression/catchphrase** — once is enough;
  focus on what **actually changed** this beat (see "State Changes Actually Caused This Beat" above). Unless this beat actually touches some part of the environment, don't describe it again.
- **Attribute accurately and stay true to the facts (equally key)**: write strictly from the "actor / other side's response / state changes" above — **who** did what and **who** was affected.
  Don't misattribute (putting one person's action on another, e.g. it should be "Qing's attempt to flank was seen through" but you write "the player has nowhere to hide");
  don't change the nature of an event (e.g. turning "the scheme was seen through" into "someone's hiding place was exposed"). Don't invent causes and effects the summary/changes don't state.
- **Never invent new entities**: describe only the people, weapons, items, and environment that already exist in the ground truth and among the present characters (a cold-weapons tavern cannot have guns or bullets, and characters who don't exist cannot appear).
- Write in a voice that matches the world tone; consequences are qualitative and reshape what can happen next (combat → injuries, negotiation → shifting loyalties, infiltration → suspicion).
- **This beat must end on an unresolved tension** (a threat, a doubt, or a choice), so someone wants to respond.
- Pacing follows tone and mode: fights can be fast, negotiation slow and soft; not everything needs combat pacing.
- Public version: only the objective events visible to everyone; **changes marked "GM secret" or "known only to that character / that faction" must never appear in the public version**.
- Private versions: only for characters who "noticed more", adding their unique perceptions in **one or two sentences** (e.g. the true meaning of a signal only their side understands); characters with no extra information can be omitted.
- **Tight and brisk (key)**: each character does one thing per beat, so narrate **that one action and its outcome** and stop. Default **2–3 sentences (about 60 words)**; only a truly pivotal beat may reach **4–5 sentences (about 100 words at most)**. Spoken lines stay short (one line per speaker). No recaps, no scenery padding.
- **Vivid but not made up**: pick one or two sharp concrete details (an expression, a sound, a consequence) from the "relevant conditions and rulings, character personality and voice" above, but **every concrete detail must come from the material above** (ground truth / relevant conditions and rulings / state changes / character voices / scene anchors); don't invent new facts or new entities.
- Write all narration in English.

Output JSON only:
{{"public":"narration visible to everyone","private":{{"character name":"that character's unique extra perception (optional; omit the key if there is none)"}}}}"""
    return await llm.call(prompt, Narration, temperature=config.TEMP_NARRATOR, max_tokens=1800)


# ───────────────── rolling summary: compress old narration for continuity (story feel only, not facts) ─────────────────
async def summarize_memory(llm: LLMClient, s: Session, cid: str,
                           old: str, evicted: list) -> str:
    name = s.cards[cid].name
    block = "\n".join(evicted)
    prompt = f"""You maintain the story-memory summary for "{name}", so they stay consistent when played later.
Merge [Existing Summary] and [Beats That Followed] into **one concise, coherent** summary.

# Existing Summary
{old or "(none; this is the first compression)"}

# New Beats (to be folded into the summary; they won't be kept verbatim afterward)
{block}

# Requirements
- Write from "{name}"'s perspective and knowledge, keeping: the direction of the plot, changes in relationships/grudges with each party, emotional ups and downs, unresolved tensions and suspense.
- **Don't record precise state data** (who is wounded where, who stands where, exact promises — those live in the ledger); you are only responsible for "story feel" and continuity.
- Concise: one paragraph, about 80 words or fewer.
- Write in English.

Output JSON only: {{"summary":"..."}}"""
    out = await llm.call(prompt, Summary, temperature=0.4, max_tokens=700)
    return out.summary


# ───────────────── ledger consolidation: merge near-duplicate entries, clear redundancy (facts unchanged) ─────────────────
async def consolidate_conditions(llm: LLMClient, s: Session, label: str,
                                 conds: list) -> list:
    """Merge near-duplicate entries describing the same thing in a list into a single entry. Returns the cleaned Condition list."""
    lines = "\n".join(f"- {c.content} | gates: {c.gates} | {c.visibility}" for c in conds)
    prompt = f"""You are tidying the "{label}" section of a tabletop RPG's state ledger: remove redundancy, but **do not change the facts**.

The entries below may include several near-duplicates describing the same thing (e.g. "pay the debt first, then we talk" appearing again and again). Please:
- **Merge** near-duplicate entries that describe the same thing **into a single concise entry**;
- Remove old entries that have been superseded or contradict each other;
- Keep facts that are **genuinely different**; don't squash different things into one entry;
- Keep each entry's gates and visibility; **don't add** facts that weren't there.
- Write in English.

Current list:
{lines}

Output JSON only: {{"conditions":[{{"content":"concise fact","gates":"how it constrains what follows","visibility":"public"}}]}}"""
    out = await llm.call(prompt, ConsolidateOut, temperature=0.2, max_tokens=1500)
    return [Condition(content=c.content, gates=c.gates, visibility=c.visibility, source="consolidated")
            for c in out.conditions]


# ───────────────── author agent: co-design a scenario with the user (block-based editing) ─────────────────
def _scenario_brief(sc: Scenario) -> str:
    w, L = sc.world, sc.ledger
    lines = [
        f"world: tone={w.tone or '(empty)'} | {len(w.laws)} laws | background {'written' if w.background else '(empty)'}",
        f"scene: location={sc.scene.location or '(empty)'} | hook {'written' if sc.scene.hook else '(empty)'} | present={sc.scene.present or '(empty)'}",
    ]
    if sc.cards:
        for cid, c in sc.cards.items():
            lines.append(f"characters[{cid}]: {c.name} ({c.faction}/{c.gender or '?'}) abilities {len(c.abilities)} / defenses {len(c.defenses)} / weaknesses {len(c.weaknesses)}")
    else:
        lines.append("characters: (none yet)")
    lines.append(f"initial state: {len(L.characters)} characters configured | spatial {len(L.scene.spatial)} | scene_facts {len(L.scene.scene_facts)} | social_facts {len(L.scene.social_facts)}")
    return "\n".join(lines)


def author_missing(sc: Scenario) -> list:
    m = []
    if not sc.world.tone:
        m.append("world tone")
    if not sc.scene.location:
        m.append("scene location")
    if not sc.scene.hook:
        m.append("opening hook")
    if not any(c.controller == "player" for c in sc.cards.values()):
        m.append("player character")
    if not any(c.faction == "enemy" for c in sc.cards.values()):
        m.append("at least one enemy")
    if not sc.ledger.characters:
        m.append("initial state (posture/speed/gauge)")
    return m


async def author_turn(llm: LLMClient, sc: Scenario, history: list, user_msg: str) -> AuthorReply:
    brief = _scenario_brief(sc)
    missing = ", ".join(author_missing(sc)) or "(the essentials look complete)"
    hist = "\n".join(f"{r}: {t}" for r, t in history[-6:]) or "(just started)"
    present_ids = ", ".join(sc.scene.present) or "(none yet)"
    prompt = f"""You are the "Writer" of a tabletop RPG, co-designing a scenario with the user. Proactively propose ideas and fill in concrete drafts rather than only asking vague questions.

# Writer's Guidelines (these determine quality)
- Character cards serve two purposes: role-play fields (personality/voice/motive/tactics) + adjudication fields (abilities/defenses/weaknesses); always fill in "gender" and appearance/age (write them into backstory) so nothing gets guessed wrong.
- **Make key weaknesses secret**: put them in the card's "weaknesses", and optionally plant clues in the ledger with visibility=gm; don't let the player know at the start (they can be discovered and exploited in play).
- World "laws" must be able to **affect adjudication** (e.g. certain masters are impervious to blades, lightness skill lets you run up walls, internal injuries heal slowly).
- **Plant hooks and tension**: the opening hook must force the player to respond immediately; use scene facts/social facts to provide stakes and variables (a debt, a hostage, a grudge, the exits sealed).
- Ledger initialization: each present character's "posture, speed (player 7 / normal 5 / fast 6 / wounded 4), perception"; set an initial gauge when needed for initiative (ambushers start high); spatial relationships and scene facts; social_facts.
- Visibility only: public / gm / faction:<faction> / self:<character id>.
- **Faction must be exactly one of "ally", "enemy", "neutral"** (player and teammates = ally, opponents = enemy, brokers/informants/bystanders and other third parties = neutral; the engine uses this to tell friend from foe, so never invent other values). Factions can change during play when characters defect or are turned; you only set the starting faction.
- Character ids are short English (e.g. player/aqing/scar); the player character's "controller" is "player", all others "agent".
- Abilities/defenses/weaknesses are always **qualitative descriptions**, **never numbers** (write "can't put strength into it when the old wound flares up", not "gauge-2").
- Write all content in English.

# Current Scenario State
{brief}
Present character ids: {present_ids}

# Still Missing / Undecided
{missing}

# Recent Conversation
{hist}

# The User's Message
{user_msg}

# Your Task (important)
**Prioritize the user's explicit request**: if it is about a character (name/personality/abilities/weaknesses/secrets/appearance), **update that character's char block** (character cards are the core of a scenario; don't keep postponing them as "to do"). With no specific direction, pick the most critical item from "Still Missing / Undecided" (usually a character card not yet created).
Understand the user's intent and **update only one block this turn**:
- block="world" → fill world (World: tone/background/laws)
- block="scene" → fill scene (Scene: id/location/hook/present)
- block="char" → fill char_id and char (one complete character card)
- block="ledger" → fill ledger (the complete initial ledger; **keep what's there and add the new**, don't drop already-configured characters)
- block="none" → just a question or suggestion, no update
Fill the corresponding block's fields **completely** and leave the other blocks' fields null. In reply, briefly say what you did or what you're asking, and guide the next step.
**Preserve existing content (important)**: when editing a block, change only what the user asked for, and **carry the block's other existing fields along unchanged** (e.g. when only changing the world laws, return tone/background as they were, don't leave them empty). The system treats empty fields as "unchanged", so there's no harm, but include them when you can; the ledger's character dict only "updates what you give and keeps what you don't".
In missing, list the key parts still missing; set done=true once "world tone + scene + hook + player + at least one enemy + basic initial state" are all in place.

Output JSON only (following the schema; fields of blocks you didn't update are null)."""
    return await llm.call(prompt, AuthorReply, temperature=0.7, max_tokens=2500)
