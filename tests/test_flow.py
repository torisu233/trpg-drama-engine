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
    sess.记忆["scar"] = [f"第{i}拍叙事" for i in range(1, 13)]   # 12 条

    async def fake_sum(grok, s, cid, old, evicted):             # 替身，避免打 API
        return f"[摘要:并入{len(evicted)}条]"
    monkeypatch.setattr(agents, "summarize_memory", fake_sum)

    asyncio.run(flow._maybe_compress(None, sess))
    assert len(sess.记忆["scar"]) == 7
    assert sess.记忆["scar"][0] == "第6拍叙事"   # 保留较新的 6~12
    assert sess.摘要.get("scar")


def test_ledger_consolidate(sess, monkeypatch):
    """账本整理：公开持久近义条目被合并；gm 条目与带 TTL 的瞬态不被动到。"""
    sess.会变层.场景.社会事实 = [
        Condition(内容=f"刀疤要求先还债#{i}", 可见性="public") for i in range(5)
    ]
    sess.会变层.场景.社会事实.append(Condition(内容="刀疤在等同伙", 可见性="gm"))
    sess.会变层.角色["player"].身心状况 = [
        Condition(内容="瞬态晕眩", 可见性="public", 剩余拍数=2)
    ]

    async def fake(grok, s, label, conds):
        return [Condition(内容="刀疤要求先清漕帮债务（合并）", 可见性="public", 来源="整理")]
    monkeypatch.setattr(agents, "consolidate_conditions", fake)

    asyncio.run(flow._maybe_consolidate(None, sess))
    社 = [c.内容 for c in sess.会变层.场景.社会事实]
    assert "刀疤要求先清漕帮债务（合并）" in 社
    assert "刀疤在等同伙" in 社                       # gm 不被整理
    assert len(社) == 2                              # 5 公开合 1 + 保留 gm 1
    assert len(sess.会变层.角色["player"].身心状况) == 1   # 带 TTL 的瞬态不整理


def test_consolidate_state_uses_lower_threshold(sess, monkeypatch):
    """身心状况用低阈值(2)：2 条近义即合并；1 条不动；场景事实仍用高阈值(4)：3 条不动。"""
    sess.会变层.角色["scar"].身心状况 = [          # 2 条公开持久 → 达状态阈值 2
        Condition(内容="恐惧加剧，可能崩溃招供", 可见性="public"),
        Condition(内容="被火逼近，惧色更甚", 可见性="public"),
    ]
    sess.会变层.角色["aqing"].身心状况 = [          # 仅 1 条 → 不达阈值 2
        Condition(内容="独一份的状态", 可见性="public"),
    ]
    sess.会变层.场景.场景事实 = [                    # 3 条公开持久 → 不达场景阈值 4
        Condition(内容=f"独立环境事实#{i}", 可见性="public") for i in range(3)
    ]

    calls = []
    async def fake(grok, s, label, conds):
        calls.append(label)
        return [Condition(内容="恐惧（已合并）", 可见性="public", 来源="整理")]
    monkeypatch.setattr(agents, "consolidate_conditions", fake)

    asyncio.run(flow._maybe_consolidate(None, sess))

    assert any("刀疤" in l and "身心状况" in l for l in calls)             # 刀疤 2 条 → 触发合并
    assert [c.内容 for c in sess.会变层.角色["scar"].身心状况] == ["恐惧（已合并）"]
    assert not any("阿青" in l for l in calls)                            # 阿青 1 条 < 2 → 不触发
    assert len(sess.会变层.角色["aqing"].身心状况) == 1
    assert "场景事实" not in calls                                        # 场景事实 3 < 4 → 不触发
    assert len(sess.会变层.场景.场景事实) == 3
