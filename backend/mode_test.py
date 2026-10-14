"""Check the non-combat mode: build a pure negotiation scene by hand and run one beat (calls the real LLM / DeepSeek).
Run: python -m backend.mode_test
"""
import asyncio
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from .models import Scenario, World, Scene, CharCard, Ledger, CharLedger, SceneLedger, Condition
from . import scenario as scen, flow, engine
from .llm_client import LLMClient


def build() -> Scenario:
    return Scenario(
        id="teahouse",
        world=World(tone="Street life and favors; information bought and sold among teahouses and taverns",
                    background="In troubled times, information is worth more than a blade.",
                    laws=["News of the martial world has a price; the shopkeeper tells each customer what they want to hear and holds out for the best offer"]),
        scene=Scene(id="teahouse", location="A private table in a teahouse in the afternoon, the neighboring tables noisy",
                    hook="Shopkeeper Qian pours the tea at his leisure: \"What you want to know, sir... doesn't come cheap.\"",
                    present=["player", "boss"]),
        cards={
            "player": CharCard(name="player", faction="ally", controller="player", gender="male",
                               backstory="A wandering swordsman seeking revenge", motive="Get the whereabouts of his enemy out of the shopkeeper",
                               abilities=["can tell when people lie", "patient"], weaknesses=["short on money"]),
            "boss": CharCard(name="Shopkeeper Qian", faction="neutral", controller="agent", gender="male",
                             backstory="Owner of the teahouse, a shrewd old man of fifty",
                             voice="Unhurried, hides meaning behind a smile, loves to push the price up",
                             motive="Make a little extra without stirring up trouble",
                             tactics=["holds out for the best offer", "sizes up the customer before naming a price", "avoids trouble"],
                             abilities=["well informed", "slippery, good at reading people"], weaknesses=["greedy", "afraid of the authorities"]),
        },
        ledger=Ledger(
            characters={
                "player": CharLedger(posture="seated across from the shopkeeper", speed=5),
                "boss": CharLedger(posture="pouring tea across the table", speed=5),
            },
            scene=SceneLedger(
                scene_facts=[Condition(content="The teahouse is crowded and noisy; outsiders can't easily overhear the conversation", visibility="public")],
                social_facts=[Condition(content="The player wants the whereabouts of his enemy; the shopkeeper hasn't named a price yet",
                                        gates="he'll only talk once a price is agreed", visibility="public")]),
        ),
    )


async def main():
    llm = LLMClient()
    s = scen.session_from_scenario(build())
    await flow.advance(llm, s)
    print(">> pending:", s.pending and s.pending.get("type"))
    print(">> Player negotiates: half the deposit now, the rest on delivery, while hinting he's not someone to cross")
    async for _ in flow.stream_action(llm, s, {
        "action": "Lowers his voice: all he wants is an address; half the deposit now, the rest once it pans out — and casually lets slip that he's not someone to cross",
        "target": "boss", "covert": False}):
        pass

    print("\n========== public_log ==========")
    for line in s.public_log:
        print(line)
    print("\n========== ledger (are the consequences social, or were injuries forced in?) ==========")
    print(engine.ground_truth(s))
    await llm.close()


if __name__ == "__main__":
    asyncio.run(main())
