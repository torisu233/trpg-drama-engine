"""Hand-written scene: a tavern on a rainy night (wuxia setting; used for v1 before the author agent existed).

Three characters:
- player player (human)
- aqing  Qing (ally, AI teammate)
- scar   Scar (enemy, AI)

Demonstrates three things:
- world laws (including hard rules that affect adjudication, like "grandmasters are impervious to blades")
- character cards with role-play traits + adjudication traits (defenses/weaknesses, hidden from opponents, discoverable and exploitable)
- planted secrets (Scar is afraid of fire = weaknesses; he's waiting for accomplices to close in = gm scene_facts)
"""
from .models import (
    Session, Scene, World, CharCard, Ledger, CharLedger, SceneLedger, Condition, Item,
)
from . import config


def new_tavern_session() -> Session:
    world = World(
        tone="Wuxia. Feuds of the martial world, flashing blades, honor above life and death, where back alleys and the imperial court intertwine.",
        background=(
            "This is an age of countless martial sects. The Canal Gang controls the lifeblood of the Grand Canal and has both "
            "the law and the underworld in its pocket; people of the martial world live by face, loyalty, and the settling of debts "
            "of gratitude and revenge. Martial skill comes in grades: true masters are shielded by their inner energy, ordinary "
            "weapons barely scratch them, and only a more refined method can touch them. In the martial world, money and lives "
            "are often worth the same."
        ),
        laws=[
            "Grandmasters of the martial arts shield themselves with inner energy, and ordinary blades, swords, fists, and kicks "
            "cannot reach their vitals; only stronger inner energy, poison, fire, striking a vital pressure point, a surprise "
            "attack on their weakness, or cutting off their foundation (crippling the source of their skill) can subdue them.",
            "Those with great lightness skill can run along eaves and up walls, closing in or escaping in an instant; those with "
            "little cannot keep up.",
            "Internal injuries are worse than external ones and slow to heal; poison and sealed pressure points take effect "
            "gradually over a few exchanges.",
            "Sometimes pressure beats fighting: reputation, leverage, or a hostage can make an enemy yield without a blow.",
        ],
    )

    cards = {
        "player": CharCard(
            name="player", faction="ally", controller="player", gender="male",
            backstory="An exiled former captain of the imperial guard in his early thirties, lean and hard, with an old wound in his left shoulder; for reasons of his own he owes the Canal Gang a debt, and his swordsmanship was learned in the army.",
            personality=["cautious", "holds grudges"],
            voice="Few words, cold and hard; speaks only when he must.",
            motive="Get out alive, and find out who is behind this debt and wants him dead.",
            tactics=["observe before striking", "makes good use of the surroundings", "never fights a battle he isn't sure of"],
            abilities=["army swordsmanship, vicious and precise up close", "sees through lies", "stays calm under pressure"],
            defenses=["a veteran of many battles, hard to rattle"],
            weaknesses=["old wound in the left shoulder; too much force and he can't put strength into it"],
        ),
        "aqing": CharCard(
            name="Qing", faction="ally", controller="agent", gender="male",
            backstory="A street tough traveling with the player, a burly man in his twenties with an enormous voice; the player once helped him out, and he has called him big brother ever since.",
            personality=["reckless", "loyal to a fault", "foul-mouthed"],
            voice="Loud, swears constantly, loves to stir things up, and gets even noisier when nervous.",
            motive="Cover his big brother (the player) and get him out in one piece, showing off a little along the way.",
            tactics=["hit first, talk later", "flip tables and smash things to cause chaos", "uses whatever is at hand as a weapon"],
            abilities=["very strong", "street brawler, fights like he has nothing to lose", "knows the tavern's layout well"],
            defenses=["thick-skinned, can take a few hits and keep going"],
            weaknesses=["simple-minded, easily goaded or tricked", "fiercely protective; will put himself in danger for the player"],
        ),
        "scar": CharCard(
            name="Scar", faction="enemy", controller="agent", gender="male",
            backstory="A second-rank enforcer of the Canal Gang, a wiry man of forty with a knife scar down his left cheek; sent to collect a debt and bring someone in.",
            personality=["cunning", "holds grudges", "bullies the weak, fears the strong"],
            voice="Smiles without warmth, loves to make threats while leaving himself a way out, and is practiced at stalling and fishing for information.",
            motive="Stall until his accomplices close the net, then take the player in one stroke, ideally without getting hurt himself.",
            tactics=["stall whenever possible, feign cooperation", "only strikes when he has the upper hand", "uses hostages/leverage to coerce"],
            abilities=["Canal Gang quick blade, vicious up close", "reads lies, changes sides with the wind"],
            defenses=["trained in iron-body technique, thick-skinned; ordinary fists and kicks barely hurt him"],
            weaknesses=[
                "afraid of fire (scarred by a childhood blaze; he instinctively recoils from open flame)",   # secret: opponents can't see character cards
                "greedy for credit and afraid to die; the moment things turn bad he saves himself first",
            ],
        ),
    }

    ledger = Ledger(
        characters={
            "player": CharLedger(
                posture="seated at a corner table, back to the wall",
                items={"dagger": Item(name="short blade", kind="weapon", traits=["sharp"],
                                     state="intact", location="hidden under his cloak")},
                speed=config.SPEED_PLAYER, perception="normal", gauge=0,
            ),
            "aqing": CharLedger(
                posture="standing at the player's side",
                speed=config.SPEED_NORMAL, perception="normal", gauge=0,
            ),
            "scar": CharLedger(
                posture="leaning back against the bar, looking down at the table",
                items={"knife": Item(name="quick blade", kind="weapon", traits=["keen edge", "fast draw"],
                                    state="intact", location="right hand resting on the hilt")},
                speed=config.SPEED_NORMAL, perception="normal", gauge=0,
            ),
        },
        scene=SceneLedger(
            spatial=[
                Condition(content="Scar has his back to the bar", gates="guards against a rear attack, but the bar limits his retreat", visibility="public"),
                Condition(content="The player sits in the corner with his back to the wall", gates="safe from behind, but no way out if cornered", visibility="public"),
            ],
            scene_facts=[
                Condition(content="The back door is locked; the only exit is the front door", visibility="public"),
                Condition(content="There is an oil lamp on the table and the stove fire is dying", gates="a source of open flame is at hand", visibility="public"),
                Condition(content="Scar is actually waiting for his accomplices to close in from outside; they can arrive within a few exchanges", visibility="gm", source="scenario"),
            ],
            social_facts=[
                Condition(content="The player owes the Canal Gang a debt, and Scar was sent to collect it", gates="Scar has a legitimate pretext; paying up or turning on him both change the situation",
                          visibility="public", source="scenario"),
            ],
        ),
        faction_private={"ally": {"plans": []}},
    )

    return Session(
        scene=Scene(
            id="tavern",
            location="A tavern on a rainy night; the stove fire is dying and the back door leads to the stable",
            hook="Scar rests one hand on his knife hilt and drawls: \"I hear you owe the Canal Gang money. How do you plan to pay tonight?\"",
            present=["player", "aqing", "scar"],
        ),
        world=world,
        cards=cards,
        ledger=ledger,
        memory={"aqing": [], "scar": [], "player": []},
        public_log=["[Scene] A tavern on a rainy night; the stove fire is dying and the back door leads to the stable",
                    "[Opening] Scar rests one hand on his knife hilt and drawls: \"I hear you owe the Canal Gang money. How do you plan to pay tonight?\""],
    )
