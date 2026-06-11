"""每拍维护：滚动摘要压缩 / 帐本整理。

这两步会调用「会打 Grok」的 agent 函式，用 pytest 内建的 `monkeypatch` 夹具把它们
换成「替身（fake）」——这是测试隔离外部依赖的标准手法。async 函式直接用 asyncio.run 跑
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
    """帐本整理：公开持久近义条目被合并；gm 条目与带 TTL 的瞬态不被动到。"""
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
