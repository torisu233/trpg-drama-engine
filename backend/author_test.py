"""Scripted test of the author agent core (calls the real LLM / DeepSeek).

Run: python -m backend.author_test
"""
import asyncio
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from .models import Scenario
from . import scenario as scen, agents
from .llm_client import LLMClient

MSGS = [
    "Wuxia scenario: a down-on-his-luck escort guard is cornered at a frontier-town inn by a treacherous swordsman, and he has a reckless, loyal female companion named Ju. Settle the world and the scene first.",
    "Create the character card for the player (the escort guard protagonist).",
    "Create the character card for the rival swordsman, and give him a secret weakness.",
]


async def main():
    llm = LLMClient()
    sc = Scenario(id="frontier_inn_test")
    history = []
    for m in MSGS:
        print("\n" + "═" * 64)
        print("User:", m)
        history.append(("User", m))
        rep = await agents.author_turn(llm, sc, history, m)
        updated = scen.apply_author_reply(sc, rep)
        history.append(("Writer", rep.reply))
        print("Writer:", rep.reply)
        print(f"→ updated block: {updated}{('/'+rep.char_id) if rep.char_id else ''} | missing={rep.missing} | done={rep.done}")

    print("\n" + "═" * 64, "\nFinal scenario summary:")
    print(agents._scenario_brief(sc))
    print("\nCard ids:", list(sc.cards.keys()), "| present:", sc.scene.present)
    print("\nFull JSON (first 2200 chars):")
    print(sc.model_dump_json(indent=2)[:2200])
    await llm.close()


if __name__ == "__main__":
    asyncio.run(main())
