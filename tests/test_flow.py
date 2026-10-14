"""每拍维护：滚动摘要压缩 / 账本整理。

这两步会调用「会打 Grok」的 agent 函数，用 pytest 内建的 `monkeypatch` 夹具把它们
换成「替身（fake）」——这是测试隔离外部依赖的标准手法。async 函数直接用 asyncio.run 跑
（保持简单，不引入 pytest-asyncio 插件）。
"""
import asyncio
from backend import flow, agents
from backend.models import Condition


def test_memory_compress(sess, monkeypatch):
    """记忆达 2W 条时，把最旧 W 条折进摘要（这里 W=5：12 → 折 5 剩 7 + 生成摘要）。"""
    sess.memory["scar"] = [f"第{i}拍叙事" for i in range(1, 13)]   # 12 条

    async def fake_sum(grok, s, cid, old, evicted):             # 替身，避免打 API
        return f"[summary:并入{len(evicted)}条]"
    monkeypatch.setattr(agents, "summarize_memory", fake_sum)

    asyncio.run(flow._maybe_compress(None, sess))
    assert len(sess.memory["scar"]) == 7
    assert sess.memory["scar"][0] == "第6拍叙事"   # 保留较新的 6~12
    assert sess.summary.get("scar")


def test_ledger_consolidate(sess, monkeypatch):
    """账本整理：公开持久近义条目被合并；gm 条目与带 TTL 的瞬态不被动到。"""
    sess.ledger.scene.social_facts = [
        Condition(content=f"刀疤要求先还债#{i}", visibility="public") for i in range(5)
    ]
    sess.ledger.scene.social_facts.append(Condition(content="刀疤在等同伙", visibility="gm"))
    sess.ledger.characters["player"].conditions = [
        Condition(content="瞬态晕眩", visibility="public", ttl=2)
    ]

    async def fake(grok, s, label, conds):
        return [Condition(content="刀疤要求先清漕帮债务（合并）", visibility="public", source="整理")]
    monkeypatch.setattr(agents, "consolidate_conditions", fake)

    asyncio.run(flow._maybe_consolidate(None, sess))
    社 = [c.content for c in sess.ledger.scene.social_facts]
    assert "刀疤要求先清漕帮债务（合并）" in 社
    assert "刀疤在等同伙" in 社                       # gm 不被整理
    assert len(社) == 2                              # 5 公开合 1 + 保留 gm 1
    assert len(sess.ledger.characters["player"].conditions) == 1   # 带 TTL 的瞬态不整理


def test_consolidate_state_uses_lower_threshold(sess, monkeypatch):
    """身心状况用低阈值(2)：2 条近义即合并；1 条不动；场景事实仍用高阈值(4)：3 条不动。"""
    sess.ledger.characters["scar"].conditions = [          # 2 条公开持久 → 达状态阈值 2
        Condition(content="恐惧加剧，可能崩溃招供", visibility="public"),
        Condition(content="被火逼近，惧色更甚", visibility="public"),
    ]
    sess.ledger.characters["aqing"].conditions = [          # 仅 1 条 → 不达阈值 2
        Condition(content="独一份的状态", visibility="public"),
    ]
    sess.ledger.scene.scene_facts = [                    # 3 条公开持久 → 不达场景阈值 4
        Condition(content=f"独立环境事实#{i}", visibility="public") for i in range(3)
    ]

    calls = []
    async def fake(grok, s, label, conds):
        calls.append(label)
        return [Condition(content="恐惧（已合并）", visibility="public", source="整理")]
    monkeypatch.setattr(agents, "consolidate_conditions", fake)

    asyncio.run(flow._maybe_consolidate(None, sess))

    assert any("刀疤" in l and "conditions" in l for l in calls)             # 刀疤 2 条 → 触发合并
    assert [c.content for c in sess.ledger.characters["scar"].conditions] == ["恐惧（已合并）"]
    assert not any("阿青" in l for l in calls)                            # 阿青 1 条 < 2 → 不触发
    assert len(sess.ledger.characters["aqing"].conditions) == 1
    assert "scene_facts" not in calls                                        # scene_facts 3 < 4 → 不触发
    assert len(sess.ledger.scene.scene_facts) == 3
