# Multi-Agent Tabletop-RPG-Style Game: Design Document

## 1. Overview

An interactive game modeled on tabletop role-playing (TRPG). Several AI agents each play a different character (allies and enemies), while a human player joins the allied side as one character, working with teammates against the enemy over many rounds of interaction. Interaction is not limited to combat: dialogue, negotiation and fighting all run through the same loop. The overall feel should be close to "a novel that is being written together."

The system has four core elements:

1. **Action intent**: every character (including the player) states "what I want to do this beat."
2. **Intent adjudication**: a neutral mechanism decides whether and how far an intent succeeds, and decides "who noticed it."
3. **Outcome narration**: the result of each interaction is written as point-of-view prose and delivered to the relevant recipients.
4. **Turn order**: an "action bar" drives the pacing and ties the other three together.

## 2. Design stance (core premise)

This project deliberately chooses **"atmosphere first, rapid prototyping, no pursuit of mechanical fairness."**

Traditional tabletop games create adversity and uncertainty with dice and numbers. This project deliberately **does not let dice or hit points decide success or failure**. It replaces a **probability engine** with a **drama engine**: tension and surprise come from opposition and dramatic stakes.

Going further, the game does not simulate the situation with numbers; its skeleton is **state and circumstance**. "A bound enemy can't fight," "a drunk enemy is harder to hit," "an enemy with his back to the wall can't be ambushed from behind": these are clumsy to simulate numerically but natural for an LLM to reason about. So the skeleton of the situation is a **discrete list of state facts (the state ledger)**, which the adjudicator agent reasons over carefully and rules on.

The replacement engine consists of:

- A genuinely tough **enemy agent** as the source of uncertainty
- An **outcome ladder** in place of hit rolls
- A qualitative **state ledger** in place of hit points
- A pinch of **luck oracle** for flavor (see Section 9)

> Numbers appear in exactly one place: **action-bar scheduling** (who acts next). They are "scheduling numbers" and never decide success or failure, so they don't contradict the philosophy above.

## 3. Roles and agent responsibilities

Responsibilities are split on purpose, so that no single agent both "knows everything" and "decides everything."

| Role | Played by | Responsibility | What it can see |
|------|-----------|----------------|-----------------|
| Enemy | Its own persistent LLM conversation | Plays a cunning, difficult opponent that does its best to threaten the allies | Only what the enemy can **currently perceive** (dynamic fog of war) |
| Teammate | Its own persistent LLM conversation | Cooperates with the player on the same side and shares the faction's plans | Allied public information + private faction plans |
| Player | Human | Plays one allied character through text input; can communicate intent covertly | Allied information + whatever their character perceives |
| GM / narrator | Neutral LLM (separate from the characters) | Writes adjudicated results as point-of-view prose and **delivers a different version to each recipient** | Receives the "ground truth" and the perception map as input; favors no side |
| Flow controller + adjudicator | Code + a neutral adjudicator agent | Advances the action bar, adjudicates intents, maintains authoritative state, decides who knows what | Omniscient, but only applies rules and takes no side |

Key points:

- **The enemy is an independent agent, not something the GM runs on the side.** The reason isn't fairness but the quality of the opposition: a GM trying to keep the whole story tidy will unconsciously pull its punches, while an enemy agent told only "you want to win, you want to threaten them" will produce moves that genuinely make the player sweat.
- **Character LLMs keep persistent conversations** (rather than being throwaway subagents re-created every beat) so they accumulate memory of this encounter.
- **Separation of powers between ordering, role-play and adjudication**: whoever decides turn order and outcomes must be neutral and cannot also play a character.
- **Character agents can never write to the state ledger directly.** They can only "state an intent" or "pass." The only writer of the ledger is the adjudicator agent.

## 4. Authoring layer: scenario generation

**Phase one: authoring (offline, iterative).** You provide a rough premise (e.g. "the party runs into enemies at a tavern"), and the author agent expands it into a structure that can be adjudicated, **planting secrets the player doesn't know** (the source of dramatic tension). The flow is **AI proposes -> you edit any field -> finalize**.

What a scenario contains (the point is "initial state ledger + secrets + fog boundaries," not just a scene description):

```
scenario = {
  scene          : "A rainy night at a tavern; the hearth is dying; the back door leads to the stable",
  cards          : [ ...see Section 5, character cards... ],
  initial_ledger : { ...see Section 5, ledger... },   // starting posture / location / items / secrets
  fog_and_secrets: {
     "Scar is afraid of fire"               : visibility gm,   // player / teammates don't know
     "Scar is waiting for backup to flank"  : visibility gm
  },
  soft_goal      : "Get Scar to reveal who hired him, and survive"   // optional; see "Ending" in Section 12
}
```

### Implementation: the author agent (conversational block editing over a shared scenario document)

A scenario is a serializable `Scenario` (world + scene + cards + initial ledger). Two editing paths share **the same canonical scenario**:

- **Manual**: edit each block directly (frontend forms).
- **Conversational**: `author_turn(current_scenario, chat_history, user_message) -> AuthorReply`. The agent is **stateless with respect to the scenario**: every turn it receives the full current scenario and **updates only one block** (`world` / `scene` / `char` / `ledger` / `none`) plus a one-line reply. The code merges that block back into the canonical copy **field by field, where an empty field means "leave unchanged"** (ledger characters are merged per key), **so the agent can't accidentally wipe existing content**.

"Stateless agent + shared canonical copy" means the frontend holds the draft, the agent always sees the latest version (including the user's manual edits), and nothing is persisted until the user saves. The agent has built-in authoring guidelines: use dual-purpose character cards, **make weaknesses `gm` secrets**, write world laws that affect adjudication, plant hooks, set initiative (initial gauge values), **use only `ally` / `enemy` factions**, and describe abilities and weaknesses qualitatively.

**Division of deletion work (deliberate)**: because "empty = unchanged," the agent can **change values, add items, and remove a single item within a field** (by returning a shorter non-empty list). **Deleting a whole character card or clearing a whole field** is left to the user in the panel. Destructive operations are clearer when done manually, and this prevents the agent from deleting things by mistake.

Interface: the frontend authoring page (editable panel on the left, chat on the right) calls `POST /api/author/turn`, which uses the same stateless core.

## 5. State model: world (static) + two-layer ledger

The core technique for keeping "lots of state" manageable is **to separate what almost never changes from what changes every beat**. Only the latter goes through the per-beat re-injection + delta loop. The changing layer is also **grouped into a nested view by subject**, so agents can consume it with little effort.

The "unchanging" part actually has two pieces: the **world** (global) and **character cards** (individual). Both are static inputs to adjudication, re-injected every beat but never modified by deltas.

### Static: the world (global laws, stored in the scenario)

Not just flavor text; it includes **hard rules that affect adjudication**:

```
world = {
  tone       : "Wuxia. Martial-world feuds, flashing blades",       // sets the GM's voice
  background : "The canal guild controls the waterways... ~200-word setting",   // grounds every agent
  laws       : [                                                    // ★ hard rules adjudication must obey
    "Masters of martial arts are protected by inner energy; ordinary blades can't reach their vital points. Only inner force, poison, fire, pressure points, exploiting a weakness or destroying their foundation can subdue them",
    "Masters of lightness skill can run along walls and close in or escape in an instant",
    "Internal injuries are worse than external ones and slow to heal"
  ]
}
```
- `tone` -> the GM's voice; `background` -> grounds every agent; **`laws` -> injected into adjudication as hard constraints on feasibility** (e.g. using an ordinary blade against a shielded master is ruled ineffective or heavily reduced).

### Static: character cards (individual, stored in the scenario, rarely changed)

**Dual-purpose fields**: half are for the character agent to role-play, half are for adjudication. **Crucially, a character's card is never injected into an opponent's context**, so the adjudication-only traits (defenses and weaknesses) are naturally known only to the adjudicator and the character itself. They are **secrets that can be discovered and exploited during play**:

```
char_scar = {
  name: "Scar", faction: "enemy",
  gender: "male",             // ★ observable basics (gender / appearance / age) -> included in views and the roster, publicly visible, so agents don't invent them wrongly
  ── role-play (read by the character agent and itself; opponents can't see) ──
  backstory  : "An enforcer for the canal guild...",
  personality: ["cunning", "holds grudges", "bullies the weak, fears the strong"],
  voice      : "A smile that doesn't reach the eyes; loves to make threats but always leaves himself an out",   // makes dialogue distinctive
  motive     : "Stall until his backup flanks them, then take them all at once",   // drives his choices
  tactics    : ["stall whenever possible", "only strike when he has the upper hand"],   // habitual methods
  ── adjudication (fully visible to the adjudicator; opponents can't see; may be secret) ──
  abilities  : ["canal-guild knife work, vicious at close range"],
  defenses   : ["iron-body training; ordinary fists and kicks barely hurt him"],   // affects adjudication: hard to hurt
  weaknesses : ["afraid of fire (secret)", "greedy for credit, afraid to die"]     // affects adjudication: exploiting them is very effective
}
```
> "Inherent traits go on the card -> fully visible to the adjudicator, known to the character, invisible to opponents." That is why a secret weakness like "afraid of fire" can be discovered and exploited by the player during play instead of being revealed up front. **Acquired or outwardly visible** states (such as losing an arm in this fight) go in the ledger.

### Layer two: the ledger (items + all kinds of state; modified only by adjudication deltas)

Grouped by subject. Each character gets a tidy block, plus a scene block and private faction blocks:

```
ledger = {
  characters: {
    char_scar: {
      posture        : "Standing with his back to the bar",
      conditions     : ["serious wound to the right ribs", "suspicious"],   // includes mental states that change behavior
      status_effects : [],                          // high-impact states: bound / imprisoned / unconscious
      items          : { item_knife: {state: "intact", location: "right hand"} },
      ── derived fields (updated by the adjudicator as it goes, used directly by code and agents) ──
      speed          : 4,                           // derived from injuries -> feeds the action bar
      perception     : "limited: distracted, prone to missing things behind him"   // derived from the serious wound -> feeds the perception map
    },
    char_player: { ... }
  },
  scene: {
    spatial      : ["Scar has his back to the bar -> can't be ambushed from behind, limited retreat"],   // relational / positional facts
    scene_facts  : ["the back door is locked", "the hearth is dying"],         // environment + revealed intel (visibility controls who knows)
    social_facts : ["Scar agreed not to attack during the negotiation -> breaking it has a cost"]   // ★ promises / agreements / alliances / confessions, with gates and visibility
  },
  faction_private: {
    ally: { plans: ["Qing draws them off while the player circles behind"] }   // stripped entirely from anything sent to the enemy
  }
}
```

**The general structure of a single state entry (`Condition`):**

```
condition = {
  content     : a natural-language fact,
  gates       : "how this constrains later actions",   // written by the adjudicator at creation, then read first (cached reasoning, prevents drift)
  severity    : optional; a qualitative tier only if it can get worse (tipsy / drunk / blind drunk, light / serious / critical wound),
  visibility  : public | faction:<faction> | self:<char_id> | gm,
  source      : which beat and which action caused it,
  lifetime    : when it expires or is cleared,
  ttl         : None = persistent; integer = expires automatically after N beats (transient; see "Long-scene maintenance" at the end of Section 5)
}
```

**Items** live in the ledger (they can be consumed or broken), but keep a "stable identity / mutable state" split to prevent name drift:

```
item_knife = {
  ── stable ── name: "Rusty short knife", kind: "weapon", traits: ["dull edge", "brittle"],
  ── mutable ── state: "intact -> chipped -> broken", location: "right hand -> on the floor", quantity: (consumables only)
}
```

### Three low-effort principles

1. **Nested grouping**: agents don't read a giant global list; they read only "the organized view of what they can perceive."
2. **Cached derived fields**: `speed` and `perception` are computed by the adjudicator as it goes; the action-bar loop and perception distribution use them directly without re-deriving them every time.
3. **Clear stable vs. mutable fields**: adjudication may only touch mutable fields; settings and inherent traits are never modified by mistake.

### Where social and informational facts live (the key to memory across long conversations)

The ledger *is* the long-term memory: **the ledger is always injected in full, never truncated** (only the narrative prose stream uses a sliding window). So "things that must be remembered" belong in the ledger, not only in prose that will eventually be cut. What conversations and negotiations produce falls into three buckets:

- **Promises / agreements / alliances / ceasefires / confessions -> added to `social_facts`** (scene level), with `gates` (the consequence of breaking it) and visibility.
- **Revealed intel (who learned what) -> reuses `scene_facts` + visibility**; no separate field (visibility already means "who knows").
- **Attitudes toward others (suspicion / wavering / trust) -> stay in `conditions`** (they are mental states); no separate field, to avoid bloat.

This way, after 10 rounds of dialogue, a confession or promise from round 1 is still valid in the ledger, and the fog is automatically correct thanks to visibility.

### Long-scene maintenance: rolling summary (narrative continuity) + transient TTL (cleanup)

Two automatic "end of beat" maintenance steps keep long scenes from blowing up the context or accumulating clutter:

- **Rolling summary (continuity)**: a character's memory = `summary (compressed older events) + the last W beats verbatim` (W = 5). When a character's memory reaches 2W = 10 entries, the oldest W are handed to the summarizer and **merged and re-compressed** into the rolling summary (per character, faithful to the fog). The summary **records only story feel, relationships, emotions and tension, not precise state** (state lives in the ledger). Only AI characters are summarized (the player is human and reads the public log).
- **Transient TTL (cleanup)**: `ttl` (None = persistent; integer = disappears after N beats). The adjudicator gives short-lived states (losing balance, being startled, spreading flames) 1-3 beats and leaves persistent ones (wounds, promises, shifts in emotion) as null; every beat the code automatically prunes entries where `turn - created_turn >= ttl`.
- **Fixing duplicate buildup at the root (implemented as a "ledger consolidation pass")**: TTL only cleans up expired transients. Near-duplicates caused by "escalating without removing the old entry" (the same confession added over and over) are fixed by the **ledger consolidation pass**: after each beat, if a list's **public, persistent** entries reach a threshold (`CONSOLIDATE_THRESHOLD` = 4 for scene lists, `CONSOLIDATE_THRESHOLD_STATE` = 2 for character `conditions`, which pile up near-duplicates faster; see `backend/config.py`), the LLM is asked to merge near-duplicates and drop redundancy. **`gm` / `self` / `faction` entries and TTL transients are never touched** (protecting the fog and TTL). It is self-regulating: consolidation shortens the list, and it only triggers again once the list grows back to the threshold. Adjudication discipline (remove the old entry when escalating) serves as a supplement.

## 6. Turn order: the action bar

Replaces rigid round-robin turns. Each character has an action bar (`gauge`) that fills by its `speed`; reaching the **threshold (20)** lets it act, and after acting it **subtracts the threshold and keeps the overflow** (fair and smooth). Speed is **derived in real time from current state**, so it reflects the fiction.

```
loop:
  everyone.gauge += speed                       // every action, everyone accumulates once
  while nobody has reached the threshold:  everyone.gauge += speed   // keep adding until someone qualifies
  actor = the character with the highest gauge among those at or above the threshold
          (ties: player first -> otherwise higher value -> otherwise fixed order fast > normal > slow)
  actor acts (player -> pause for input; NPC -> agent produces an intent)
  -> two-axis check -> adjudication -> narration -> distribution
  actor.gauge -= threshold                      // keep the overflow, don't reset to zero
```

> **Why keep the overflow instead of resetting to zero**: as long as each action subtracts the threshold and keeps the overflow, over time "ratio of actions = ratio of speeds," which is clean and predictable. Resetting to zero discards the overflow and distorts the ratio. This rule is the key to the fairness of the whole mechanism.

Speed values (base range kept tight at 4-7 so the turn order doesn't spread too far; only extreme states drop below):

| Current state | Speed | Long-run share of actions | Relative to player |
|---|---|---|---|
| Player (slightly higher by default) | 7 | 32% | 1.0x |
| Fast (agile, alert) | 6 | 27% | 0.86x |
| Normal | 5 | 23% | 0.71x |
| Slow (wounded / drunk / encumbered) | 4 | 18% | 0.57x |
| Seriously wounded | 3 | - | below range |
| Near death / pinned down | 2 | - | below range |
| Unconscious / tightly bound | ~0 | - | naturally never gets a turn |

Design effects:

- **Turn order doesn't spread too far**: in the normal 4-7 range, the slowest character still acts 57% as often as the player, so nobody is left out, and the player is clearly the most active.
- **Only severe states really slow you down**: everyday variation is kept tight, but serious wounds and near-death drop below the range, so taking damage genuinely costs tempo.
- **An unconscious character has speed ~0, so their bar never fills and they never get a turn.** Structure replaces a "forced skip." If they somehow do get a turn, the agent knows it is unconscious and plays it as "unable to move." **There is no hard skip flag; agents are trusted to understand their own state.**
- **Speed tracks the fiction in real time**: speed is read from the ledger's derived `speed` field, so as soon as someone is seriously wounded, they slow down on the very next tick. The action economy follows the situation automatically.
- **Initiative is seeded by initial values**: if everyone starts at 0, the player always acts first. For an ambush, the scenario gives the ambusher a high initial gauge (e.g. 15) so the enemy gets the opening move. Initiative is expressed through the "initial value," not by changing base speed.
- **Optional knob**: the "cost" of an action can vary: an all-out heavy strike subtracts more (your next turn comes later), a light move subtracts less. This adds tactical texture without touching success numbers.

## 7. The adjudicator agent: the hub of action and knowledge

The adjudicator agent is the authoritative core of the whole system, with **two equally important responsibilities**:

- **Action management**: decide whether an intent is feasible in the current state and how far it succeeds, and express the result as additions, removals and modifications to the state ledger (a delta).
- **Knowledge management**: decide **who noticed this and how much**, producing a perception map that maintains and dynamically adjusts the fog of war.

Both must be neutral and auditable, so **structured output forces an inspectable chain of reasoning**. This stops it from cutting corners, overlooking state, or being talked into things by a character's rhetoric (e.g. the enemy agent slipping "I already slipped out of the ropes" into its intent: the adjudicator must treat the ledger as the only source of truth and reject any fait accompli that hasn't been adjudicated).

### Mandatory reasoning protocol (the adjudicator's dual output)

```
Adjudication input: this beat's action intent (+ the other side's reaction intent, if collected)
        + world laws + the full state ledger (ground truth, including every character's inherent traits: abilities / defenses / weaknesses)
        + luck oracle result (if contested)

Adjudication output (mandatory schema):

A. Action ruling
  1. relevant_conditions : ["char_scar.status_effects: hands tied behind his back", "scene.spatial: back to the bar"]
        └ forces it to list which relevant states it "sees"; it may not ignore them
  2. rulings :
        hands tied behind his back -> "blocks" (can't attack with a weapon)
        back to the bar            -> "rewrites" (no room to get behind him)
  3. feasibility : impossible / hindered / feasible / needs_rewrite
  4. outcome     : success / success_with_cost / reversal   (the outcome ladder; see Section 9)
  5. ledger_delta: { add: [...], remove: [...], modify: [...] }   // the only authoritative state change

B. Knowledge ruling
  6. perception_map : {
        char_scar (seriously wounded, distracted) : "none",              // doesn't notice movement behind him
        char_boss                                 : "all: sees the player move",
        ally_qing (teammate)                      : "all + understands the signal's real meaning"
     }

C. A one-line ground-truth summary for the GM (gm_summary)
```

What this protocol achieves:

- **Steps 1 and 2 force it to look at all relevant state, world laws and inherent traits.** It can't ignore "bound" and rule an attack successful, nor ignore laws and traits like "shielded, hard to hurt" or "afraid of fire" (an ordinary blade against a shielded opponent must be ruled ineffective or heavily reduced; hitting a weakness is very effective).
- **Step 5 makes state changes explicit**: the situation can only change through a delta, never drift quietly in prose. The lasting consequences of dialogue and negotiation (confessions, promises, alliances, intel) are also recorded by `ledger_delta` as `social_facts`, not only physical state.
- **Step 6 puts "who knows what" under adjudication**: only the adjudicator, which sees the whole state, is qualified to judge perception. As a result the fog can narrow dynamically with serious wounds, blindfolds and unconsciousness.
- **The whole chain can be audited by code or a lightweight check**: if it rules "attack succeeds" without addressing "bound" in step 2, that is a missed ruling.

## 8. The two-axis check for actions: reactions and contested actions

Before an action reaches adjudication, the code checks it along **two independent axes**. Both often apply at once, but **they are not the same thing** and must be handled separately:

| Axis | Question | Decides |
|---|---|---|
| **A. Collect a reaction?** | Does the other side need to respond before adjudication? | Whether to collect an extra "reaction intent" |
| **B. Is it contested?** | Is the outcome genuinely uncertain? | Whether to roll the luck oracle |

Examples: attacking an alert enemy = yes on both; retreating with nobody in the way = no on both; retreating while being pressed hard = no reaction, but contested.

### Axis A: does the other side react first?

**Core principle: collect a reaction only when "the outcome depends on a choice the defender makes right now, about something they can perceive."** It passes three gates:

1. **Can the other side perceive it?** If they can't perceive it, they can't react. Ambushing an enemy from behind who hasn't noticed you -> no reaction; adjudication treats it as a surprise attack. (This echoes Section 10: **you can only react to what you notice.**)
2. **Can the other side meaningfully resist?** Bound, unconscious or incapacitated characters can't react; adjudication rules directly.
3. **Is the other side the player?** If so, the player **always** gets to react. This is the lifeline of "every beat ends on a threat": an enemy attacks -> the player must respond, and the beat's hook forms naturally.

> **Timing and "when in doubt, collect"**: reactions are collected *before* adjudication, but whether the other side actually perceived the action is only settled *during* adjudication. The code's pre-check uses the derived `perception` field as a rough filter and **always collects when it's ambiguous**; if adjudication later decides they didn't notice, it rules the reaction void. Better to collect too many than to miss one.

**Key constraint: a reaction is an intent, not a verdict.** The defender can say "I dodge" or "I agree out loud while planning to turn on them," but **cannot declare success or failure**. Adjudication weighs `action intent x reaction intent x state x luck` together, and considers the defender's state and the attacker's leverage (e.g. holding something over them = an entry in the ledger) before deciding. Otherwise a persuaded enemy could undo everything with a single "I'm unmoved."

> **A reaction is an interrupt**: the defender reacts in order to defend, and this **does not consume their own action-bar turn** (optional knob: only a desperate rolling dodge costs a bit of gauge). So "the enemy attacks -> the player is forced to respond" doesn't disrupt the action-bar economy; it is its heartbeat.

### Axis B: what counts as contested?

- **Uncontested (no luck roll, adjudicate directly)**: the outcome is determined by the state:
  - Clearly feasible: retreating with nobody in the way, picking up the knife at your feet.
  - Clearly impossible: a bound character throwing a punch, persuading an unconscious person.
- **Contested (roll the luck oracle)**: the outcome is genuinely uncertain, usually because:
  - (a) the other side can perceive it and actively resist (attacking or persuading an alert enemy); or
  - (b) **the environment itself is the gamble** (leaping a gap between roofs on a rainy night, picking a lock under pressure). These **have no opponent but are still contested**.

### Walkthrough

- **(1) Attacking an alert enemy**: Axis A yes (perceives, can resist) -> collect a reaction; Axis B yes -> roll luck. Adjudication resolves the `attack x defense` conflict.
- **(2) Persuading an enemy**: Axis A yes -> collect a reaction (but the reaction is a *stance* such as resisting, wavering or feigning compliance, not a verdict); Axis B usually yes. Adjudication weighs the enemy's suspicion or fear plus the persuader's leverage, and often rules `success_with_cost`.
- **(3) Stepping back a few paces mid-fight** (two cases):
  - **Nobody pressing**: Axis A no, Axis B no -> no reaction, no luck roll; adjudication just lightly updates `posture` in one line.
  - **Pressed hard by an enemy**: Axis A **no** (the retreat isn't aimed at the enemy; whether to pursue is the enemy's own decision on *its own turn*), Axis B **yes** (contested by the environment; roll luck). Adjudication uses the outcome ladder to set the cost: `success_with_cost` (gets distance but leaves an opening and takes a cut) or `reversal` (gets driven into a corner).

> Why does a retreat *not* collect the enemy's reaction while an attack *does*? An attack's outcome **depends directly** on the defender's choice to dodge or block in that moment; a retreat's outcome depends on the **environmental situation** (relative positions, whether someone is pressing), which adjudication can judge from the ledger. The enemy's "pursuit" happens actively when its action bar comes up.

### Two-axis flow for a single beat

```
Actor's intent (attack / persuade / retreat ...)
   │
   ▼
[Code] Axis A: should the other side react? (perceives + can resist, or is the player)
        yes -> collect the other side's reaction intent (pause for input if it's the player)
        no  -> skip (surprise attack / incapacitated target / action without a target)
   │
   ▼
[Code] Axis B: contested?  yes -> roll the luck oracle (hidden)
   │
   ▼
[Adjudicator] rule on "action intent x (reaction intent) x state x luck" -> outcome ladder
        -> ledger_delta + perception_map
   │
   ▼
[GM] per-recipient narration -> distribution
```

## 9. Mechanics that replace dice

### 1. Action intent

- Every character outputs only a **decision** each beat, in a structured format. The prototype uses **three lean fields**: `{ action: "Flip the table into Scar", target: "Scar", covert: false }`.
  - `action`: one sentence describing "what I want to do (**including how**)." The original idea split this into "action type + method," but in practice players tended to repeat themselves across the two fields, and an LLM understands a single complete sentence just fine, so they were merged. Method details (where to hit, with what, using the environment, timing) go in this sentence, and they are what actually changes the ruling.
  - `target`: the **primary target** (a character id, or empty); the code uses it to decide whom Axis A collects a reaction from. It is the "primary target," not the "only character involved."
  - `covert`: whether the actor wants to **hide it from the enemy** (an information dimension, independent of the contested "does it succeed" dimension). When true, adjudication splits it into cover and real meaning and decides whether it is detected. Sneaking, signals and quietly drawing a blade fall here.
- **Limited compounding**: one beat may contain "one main action + one small side action" (attack while signaling, retreat while taunting), written in the same `action` sentence. Adjudication rules on each part and weighs the cost of splitting attention (`success_with_cost`); the side target (e.g. the teammate receiving the signal) is handled by the perception map with no separate reaction. Don't overdo it: one or two things at most.
- An intent says only "what I want to do" and **never declares success or failure**. The enemy LLM may not say "I hit him": adjudication isn't in the characters' hands.

### 2. The outcome ladder (replaces hit rolls)

Adjudication doesn't roll dice; it picks the result from the ladder that is **most dramatic while being the most plausible within the established fiction**:

- **success**
- **success_with_cost**
- **reversal**

The choice is driven by drama and plausibility. Key principle: **clean successes are rare.** Most actions come back as "you did it, but...", and that "but" is the fuel that keeps the scene rolling. Every outcome lands as a `ledger_delta`.

### 3. Narration principles (written into the GM's system prompt)

- **Consequences are qualitative and change capabilities**: don't write "loses a few HP," write "after the cut to his right arm he can only use his left" or "the weapon breaks." Every outcome rewrites what can be done next.
- **Every beat ends on a threat or a choice**: keeps it a back-and-forth rather than a monologue.
- **Elastic time**: a dull standoff gets one line; a decisive blow is broken into slow motion. Concentrate the firepower on the turning point.
- **Rich but not invented**: besides the one-line GM summary, the narrator receives the adjudication's **relevant conditions / per-condition rulings** and **the personality and voice of the characters on stage**, and uses them to develop dramatic key beats into a full paragraph (expressions, actions, actual dialogue, emotion), with length matched to weight. But every detail **must come from these existing facts**; nothing may be invented. Character intents can also be layered (including actual dialogue and demeanor).
- **Stay close to the point of view**: write the character's fear, judgment and pain.
- **Per-recipient distribution**: following the perception map, write each recipient their own private version.
- **Accurate attribution**: follow "actor / response / state changes" strictly when writing who did what and who was affected; never mix up characters or change the nature of an event (e.g. turning "someone's scheme was seen through" into "someone had nowhere to hide").
- **Only this beat's new developments**: the narrator receives "the public narration from the last 1-2 beats" as story context and must **continue from it without repeating** events or dialogue already written; if this beat is just a continued standoff, write only the new details. This is the lifeline of narrative quality (narration is what the player reads most).

### 4. The state ledger is the situation (replaces hit points)

The ledger from Section 5 is the authoritative record of the situation. Every adjudication updates it, and later actions are **constrained by it** (a wounded arm can't deliver a heavy blow; someone backed against a wall has nowhere to retreat).

### 5. The luck oracle (rolled for every contested action)

On **contested actions** (see Axis B in Section 8), the code rolls a coarse qualitative luck value (`bad_luck / even / good_luck`). It is **fed to the adjudicator as biasing text**, not as a hit chance:

- `bad_luck` -> adjudication moves the outcome down one rung, or invents an unlucky complication ("the knife slips on spilled wine").
- `good_luck` -> allows a rare clean success, or an unexpected favorable twist.
- **How the bad or good luck manifests is decided by the adjudicator within the fiction**, keeping it plausible.
- Luck is **hidden from character agents**; only the adjudicator sees it, otherwise the enemy agent would game it.

Uncontested actions don't roll; they are adjudicated directly.

## 10. Knowledge and fog-of-war model

**Premise: a single scene, with everyone acting in the same place.** So most physical actions are **visible to everyone (`public`)**, and fog is the exception rather than the skeleton. Private information comes from only three sources:

1. **Secrets prepared by the scenario** (`gm` visibility): weaknesses, hidden intentions, concealed items. Hidden from the start and revealed through play.
2. **Facts the scenario makes discoverable by a single faction**: avoids having to adjudicate "who found out" for every faction every time; by default a fact belongs to one faction.
3. **Signals (cover / real meaning)**: the cover is visible to everyone, but only the same faction understands the real meaning; others see it without knowing what it means.

On top of that sits a layer of **dynamic perception modifiers** (secondary, the exception): someone blindfolded, unconscious or distracted by a serious wound may miss even public actions.

### 1. Cover and real meaning (split by adjudication)

For example, the player signals a teammate under the table: the enemy can see the hand move (the cover) but doesn't understand it (the real meaning):

```
Player action: hand signal under the table
  cover       : "The player's fingers twitch at the edge of the table"   // visible to everyone
  real meaning: "Signals Qing to circle behind Scar"                    // only allies understand
```

**Character agents only supply "intent + a flag that they want it hidden"; actually splitting it into cover and real meaning, and judging whether the concealment works, is the adjudicator's knowledge-management job.** Corollary: **concealment can fail.** Sharp-eyed Scar might read your signal, and that is decided by adjudication, not automatic.

**Adjudication order and fields** (`Adjudication.detected: bool` / `cover: str`): for actions flagged as covert, adjudication **first decides whether it is detected**:
- Gets away with it (`detected=false`) -> generates a one-line `cover` that onlookers take at face value (a disguised visible action); the real meaning is understood only by the same faction (via visibility / the perception map).
- Detected (`detected=true`) -> `cover` is left empty; the truth is exposed and narrated as it really is.

The visible "action text" chip in the player's view is routed accordingly (`engine.visible_action_text`): **open actions (including enemy ones) always show the real action**. For covert actions, if the actor is an ally -> show the real action (the player is in on it); if enemy or neutral -> show nothing before adjudication, show the `cover` if it got through, show the real action if detected (if adjudication forgets to fill in the cover, it falls back to hiding the action, never to leaking the real meaning). When a covert enemy action targets the player and collects a reaction, the player's incoming prompt gives a non-revealing warning (without leaking the real meaning; refining the reaction axis for this case is future work).

### 2. Dynamic perception modifiers (the exception layer)

- Unconscious -> receives nothing.
- Blindfolded -> no sight, but can hear.
- Distracted by a serious wound -> may miss others' small movements.

What each recipient "receives" is determined by their derived `perception` field, and adjudication rules per person in the perception map (`all` / `partial` / `none`). This also directly drives Axis A in Section 8: **someone who can't perceive an action can't react to it.**

### 3. Private faction information and covert coordination

- A faction plan is a state entry with `visibility = faction:ally`, usually preset by the scenario or produced by private discussion; it is stripped entirely from anything sent to the enemy (the enemy might see the allies whispering, but not what they said).
- **The "private discussion" action**: the player and teammates talk on a channel whose content the enemy can't see, and the agreed plan is written down as a faction plan. Private discussion **does not advance the action bar**; its result is committed to the ledger by adjudication.
- Information boundary between teammates and the player: teammates see the player's public actions and the faction plans, but the player's private reasoning isn't necessarily fed to the teammate agent.

## 11. Role contracts and information boundaries

Pinning down each role's "what it does / what it knows / what it produces" as an implementation contract:

| Role | What it does | What it knows | What it produces |
|---|---|---|---|
| Author agent (offline) | Expands the scenario, fills in state, plants secrets, sets initial values | The player's rough premise + general knowledge (an omniscient creator) | A scenario file: **world (tone / background / laws)** + **dual-purpose cards[]** (role-play fields + adjudication traits) + initial ledger (including derived fields, initial gauge values and social facts) + fog secrets + soft goal |
| Flow controller (code, not an LLM) | Advances the action bar, runs the two-axis pre-check, rolls luck, filters and distributes through the fog, pauses for the player, applies deltas, decides when the scene ends, hosts private discussion | Omniscient, but only applies rules; never adjudicates | The actor, the luck value, each side's view, pause points, the updated ledger |
| Character agent (enemy / ally) | Produces action and reaction intents, may pass, may make covert intents, takes part in private discussion | Only "what the perception map allows + its own memory"; allies additionally see faction plans | Structured intents and reactions; **never declares success or failure** |
| Adjudicator agent | Action ruling + knowledge ruling, updates derived fields, writes the GM summary | Full ground truth + intent (+ reaction) + luck | Dual output: `ledger_delta` + `perception_map` + `gm_summary` |
| GM / narrator agent | Writes point-of-view prose per recipient, ends on a threat, attributes accurately, writes only this beat's new developments | GM summary + perception map + this beat's actor / response / state changes + recent narration (story so far) + public scene anchors | 1 public narration + N private narrations |

### Six settled boundary rules

1. **When in doubt, collect the reaction**: if Axis A is ambiguous, always collect; adjudication can void it afterwards. Better too many than one missed.
2. **Cover and real meaning are decided by adjudication**: characters only flag "I want this hidden"; adjudication splits it and judges whether the concealment works (**it can be detected**).
3. **Initial values are set by the author**: the derived `speed` / `perception` fields and the initial gauge values all come from the scenario; afterwards adjudication maintains them and the code only reads the cache.
4. **Sources of private information (single-scene premise)**: scenario-preset secrets (`gm`) / facts the scenario makes discoverable by one faction / signals (cover visible, real meaning not) / **inherent traits on character cards (known to the adjudicator and the character, invisible to opponents, discoverable and exploitable during play)**. Dynamic "who found out" rulings at runtime are rare.
5. **The GM writes, the code delivers**: the GM only writes the various versions of the prose; **the code routes them into the right memories according to the perception map**. Maintaining the fog boundary is always the code's responsibility.
6. **The ledger always wins**: when a character's memory conflicts with the authoritative ledger, **the ledger written by adjudication** wins. Re-injecting each agent's visible view every beat automatically corrects drift.

## 12. Turn flow overview

```
[Authoring] Author agent ── offline, iteratively produces the scenario (initial ledger + secrets + fog)
        │
────────  real-time loop below, driven by the action bar  ────────
        ▼
[Code] action bar accumulates -> pick this beat's actor (player first on ties)
        │
        ▼
[Character LLM / player] produces an action intent (only what it wants to do; may be compound or covert)
        │
        ▼
[Code] two-axis check:
        Axis A, collect a reaction? -> if so, collect the other side's reaction intent (pause for input if it's the player)
        Axis B, contested?          -> if so, roll the luck oracle (hidden)
        │
        ▼
[Adjudicator agent] mandatory reasoning protocol:
        action ruling (outcome ladder + ledger_delta)
        + knowledge ruling (perception_map)        <- action and knowledge weighted equally
        │
        ▼
[GM / narrator LLM] following the perception map, writes prose per recipient (ending on a threat)
        │
        ▼
[Code] public narration to everyone / private results fed back into each conversation's memory (maintaining the dynamic fog)
        │
        └──────> actor's action bar is reduced, back to accumulation
```

**How the scene "ends"** (a novel-style flow has no hard HP = 0 ending):

- The scenario's soft goal is reached (the employer is revealed, everyone gets out alive); or
- The player calls it; or
- The tension has fully dissolved and there's no unresolved threat left to continue.

## 13. Implementation notes

- **Mode-neutral (prompts aren't biased toward combat)**: the adjudicator, narrator and character prompts don't hard-code combat instructions like "suppress the threat." Characters act on **their own motives**, with methods that fit the situation. Dialogue and negotiation, disguise and infiltration all use the same machinery (state + outcome ladder + social facts + covert perception), with **qualitative consequences** suited to the mode: negotiation records trust, concessions and leverage (social facts); infiltration hinges on whether you are detected (covert perception); only combat writes wounds. Narration "ends on unresolved tension" (a threat, a doubt or a choice, not only threats).
- **Character memory**: the enemy and the teammate each keep a persistent conversation history that is appended every beat, so memory accumulates naturally. The fog boundary is drawn by the code: when distributing the situation, each side only gets what the perception map allows.
- **Structure everything**: intents, reaction intents, adjudication output (action delta + perception map) and state entries all use structured output with fixed schemas, so the code can parse and audit them.
- **Put rules and checks in code wherever possible** (two-axis pre-check, legality checks, action-bar advancement, luck rolls, fog filtering); **give the careful reasoning to the adjudicator agent** (outcome-ladder choice, state deltas, perception rulings); **give the polish to the GM**.
- **Human input**: whenever the action bar reaches the player, or the player is asked for a reaction, the loop stops and waits for input. This is the main reason to keep a thin code framework (an autonomous agent's instinct is to run straight to the end; it has to be fenced in).
- **Adjudication cost**: each contested beat can involve several LLM calls (action intent + reaction intent + adjudication + GM). That is an inherent cost of this approach.
- **Reuse from the earlier ai-word prototype**: `ActionAnalyzer` (intent parsing), `ReactionJudge` (reaction collection, corresponding to Axis A in Section 8), `NarrativeGenerator` and `BattleEngine` (flow coordination) can largely be reused; `CombatCalculator`'s numeric calculations are replaced entirely by "adjudicator agent + state ledger"; `BattleState` is replaced by the two-layer state model. What's new is the persistent character-agent conversations and the dynamic fog distribution layer.
- **LLM client**: all LLM calls go through `backend/llm_client.py` (`LLMClient`), which returns schema-validated structured outputs.

## 14. One-line summary

Replace the **probability engine** of "dice + numbers" with a **drama engine** of "adversarial agents + outcome ladder + state ledger":
**Code owns order and framework, the adjudicator agent owns whether actions succeed and who knows what, character LLMs own what they want to do, and the GM owns telling it well to each person.**
