"""純邏輯煙霧測試（不需 Grok API）。
驗證：行動條節奏、迷霧過濾、兩軸判定、delta 套用。

執行：  python -m backend.smoke_test
"""
import asyncio
from .scene import new_tavern_session
from . import engine, flow, agents, config
from .models import Intent, Condition, Adjudication, LedgerDelta, DeltaItem


def t_action_bar():
    s = new_tavern_session()
    counts = {"player": 0, "aqing": 0, "scar": 0}
    seq = []
    for _ in range(30):
        actor = engine.pick_actor(s)
        counts[actor] += 1
        seq.append(actor)
        engine.consume_turn(s, actor)
    assert all(v > 0 for v in counts.values()), f"有人挨餓: {counts}"
    assert counts["player"] >= counts["aqing"], f"玩家應最活躍: {counts}"
    assert seq[0] == "player", f"玩家應先手: {seq[:3]}"
    print(f"[行動條] 30 拍分布 {counts} 前八拍 {seq[:8]}  ✓")


def t_fog():
    s = new_tavern_session()
    view = engine.build_view(s, "player")
    assert "怕火" not in view, "玩家不該看到 gm 秘密(怕火)"
    assert "等同夥" not in view, "玩家不該看到 gm 秘密(包抄)"
    assert "後門上鎖" in view, "玩家應看到公開事實"
    assert "短刃" in view, "玩家應看到自己的物品"
    gt = engine.ground_truth(s)
    assert "怕火" in gt and "等同夥" in gt, "裁決的地面真相應含 gm 秘密"
    print("[迷霧] 玩家視圖隱藏 gm 秘密、裁決可見全貌  ✓")


def t_two_axis():
    s = new_tavern_session()
    # 攻擊清醒的敵人 → 收反應 + 爭議
    atk = Intent(actor="player", 行動="攻擊", 目標="scar", 方式="掀桌撞他")
    assert engine.needs_reaction(s, atk) == "scar", "攻擊清醒敵人應收反應"
    assert engine.is_contested(s, atk, "scar") is True, "攻擊應為爭議"

    # 攻擊被綁的敵人 → 不收反應
    s.會變層.角色["scar"].特殊情況.append(Condition(內容="雙手被反綁", 可見性="public"))
    assert engine.needs_reaction(s, atk) is None, "被綁者無法反應，不應收反應"

    # 無對象後撤 → 不收反應、非爭議
    retreat = Intent(actor="player", 行動="後撤", 目標=None, 方式="退兩步")
    assert engine.needs_reaction(s, retreat) is None
    assert engine.is_contested(s, retreat, None) is False, "平靜後撤非爭議"

    # 環境賭注（無對手仍爭議）
    leap = Intent(actor="player", 行動="跳過裂縫", 目標=None, 方式="助跑起跳")
    assert engine.is_contested(s, leap, None) is True, "跳躍應為環境爭議"
    print("[兩軸] 反應收集 / 爭議判定 全部符合預期  ✓")


def t_delta():
    s = new_tavern_session()
    adj = Adjudication(
        結果階梯="成功但有代價",
        ledger_delta=LedgerDelta(add=[
            DeltaItem(主體="scar", 類別="身心狀況", 內容="右肩中刀",
                      gates="右手使不出重擊", 可見性="public"),
        ]),
        速度更新={"scar": 3},
    )
    engine.apply_delta(s, adj)
    blob = " ".join(c.內容 for c in s.會變層.角色["scar"].身心狀況)
    assert "右肩中刀" in blob, "delta add 應生效"
    assert s.會變層.角色["scar"].行動速度 == 3, "速度更新應生效"
    print("[delta] 狀態增刪與衍生欄更新生效  ✓")


def t_expire():
    s = new_tavern_session()
    s.回合數 = 5
    engine.apply_delta(s, Adjudication(ledger_delta=LedgerDelta(add=[
        DeltaItem(主體="scar", 類別="身心狀況", 內容="被火光驚嚇後退", 剩餘拍數=2),
        DeltaItem(主體="scar", 類別="身心狀況", 內容="右肋重傷"),   # 剩餘拍數 None = 持久
    ])))  # 創建回合=5
    blob = lambda: " ".join(c.內容 for c in s.會變層.角色["scar"].身心狀況)
    s.回合數 = 6; engine.expire_transients(s)
    assert "被火光驚嚇後退" in blob(), "剩餘2拍，第6回合(差1)應還在"
    s.回合數 = 7; engine.expire_transients(s)
    assert "被火光驚嚇後退" not in blob(), "剩餘2拍，第7回合(差2)應過期"
    assert "右肋重傷" in blob(), "持久狀態(None)不該過期"
    print("[TTL] 瞬態自動過期、持久狀態保留  ✓")


async def _t_compress():
    s = new_tavern_session()
    s.記憶["scar"] = [f"第{i}拍敘事" for i in range(1, 13)]   # 12 條
    async def fake_sum(grok, sess, cid, old, evicted):       # 替身，避免打 API
        return f"[摘要:併入{len(evicted)}條]"
    orig, agents.summarize_memory = agents.summarize_memory, fake_sum
    try:
        await flow._maybe_compress(None, s)
    finally:
        agents.summarize_memory = orig
    assert len(s.記憶["scar"]) == 7, f"12 條應摺出 5 剩 7：{len(s.記憶['scar'])}"
    assert s.記憶["scar"][0] == "第6拍敘事", "保留的應是較新的 5~9 條"
    assert s.摘要.get("scar"), "應產生摘要"
    print(f"[摘要] scar 記憶 12→{len(s.記憶['scar'])} 條 + 生成摘要（evict 最舊 {config.KEEP_RECENT} 條）  ✓")


def t_compress():
    asyncio.run(_t_compress())


if __name__ == "__main__":
    t_action_bar()
    t_fog()
    t_two_axis()
    t_delta()
    t_expire()
    t_compress()
    print("\n全部純邏輯煙霧測試通過 ✅（行動條/迷霧/兩軸/delta/TTL/摘要）")
