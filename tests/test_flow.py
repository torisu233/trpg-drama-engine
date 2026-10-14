"""Per-beat upkeep: rolling summary compression / ledger consolidation.

Both steps call agent functions that would hit the LLM; pytest's built-in `monkeypatch` fixture swaps them for
fakes — the standard way to isolate external dependencies in tests. Async functions run via asyncio.run
(kept simple, no pytest-asyncio plugin).
"""
import asyncio
from backend import flow, agents
from backend.models import Condition


def test_memory_compress(sess, monkeypatch):
    """When memory reaches 2W entries, fold the oldest W into the summary (here W=5: 12 → fold 5, keep 7 + a summary)."""
    sess.memory["scar"] = [f"beat {i} narration" for i in range(1, 13)]   # 12 entries

    async def fake_sum(llm, s, cid, old, evicted):              # fake, avoids calling the API
        return f"[summary: merged {len(evicted)} entries]"
    monkeypatch.setattr(agents, "summarize_memory", fake_sum)

    asyncio.run(flow._maybe_compress(None, sess))
    assert len(sess.memory["scar"]) == 7
    assert sess.memory["scar"][0] == "beat 6 narration"   # keeps the newer 6-12
    assert sess.summary.get("scar")


def test_ledger_consolidate(sess, monkeypatch):
    """Ledger consolidation: public persistent near-duplicates are merged; gm entries and transients with a TTL are left alone."""
    sess.ledger.scene.social_facts = [
        Condition(content=f"Scar demands the debt be paid first #{i}", visibility="public") for i in range(5)
    ]
    sess.ledger.scene.social_facts.append(Condition(content="Scar is waiting for his accomplices", visibility="gm"))
    sess.ledger.characters["player"].conditions = [
        Condition(content="momentarily dizzy", visibility="public", ttl=2)
    ]

    async def fake(llm, s, label, conds):
        return [Condition(content="Scar demands the Canal Gang debt be settled first (merged)", visibility="public", source="consolidated")]
    monkeypatch.setattr(agents, "consolidate_conditions", fake)

    asyncio.run(flow._maybe_consolidate(None, sess))
    social = [c.content for c in sess.ledger.scene.social_facts]
    assert "Scar demands the Canal Gang debt be settled first (merged)" in social
    assert "Scar is waiting for his accomplices" in social   # gm entries aren't consolidated
    assert len(social) == 2                          # 5 public merged into 1 + 1 gm kept
    assert len(sess.ledger.characters["player"].conditions) == 1   # transients with a TTL aren't consolidated


def test_consolidate_state_uses_lower_threshold(sess, monkeypatch):
    """Character conditions use the low threshold (2): 2 near-duplicates merge, 1 is left alone; scene facts keep the high threshold (4): 3 are left alone."""
    sess.ledger.characters["scar"].conditions = [          # 2 public persistent → reaches the state threshold of 2
        Condition(content="fear intensifying, may break and confess", visibility="public"),
        Condition(content="the fire draws closer, his fear deepens", visibility="public"),
    ]
    sess.ledger.characters["aqing"].conditions = [          # only 1 → below the threshold of 2
        Condition(content="a one-of-a-kind state", visibility="public"),
    ]
    sess.ledger.scene.scene_facts = [                    # 3 public persistent → below the scene threshold of 4
        Condition(content=f"independent environment fact #{i}", visibility="public") for i in range(3)
    ]

    calls = []
    async def fake(llm, s, label, conds):
        calls.append(label)
        return [Condition(content="fear (merged)", visibility="public", source="consolidated")]
    monkeypatch.setattr(agents, "consolidate_conditions", fake)

    asyncio.run(flow._maybe_consolidate(None, sess))

    assert any("Scar" in l and "conditions" in l for l in calls)              # Scar has 2 → triggers a merge
    assert [c.content for c in sess.ledger.characters["scar"].conditions] == ["fear (merged)"]
    assert not any("Qing" in l for l in calls)                             # Qing has 1 < 2 → no merge
    assert len(sess.ledger.characters["aqing"].conditions) == 1
    assert "scene_facts" not in calls                                        # scene_facts 3 < 4 → no merge
    assert len(sess.ledger.scene.scene_facts) == 3
