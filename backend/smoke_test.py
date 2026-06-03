"""純邏輯煙霧測試（不需 Grok API）。
驗證：行動條節奏、迷霧過濾、兩軸判定、delta 套用。

執行：  python -m backend.smoke_test
"""
from .scene import new_tavern_session
from . import engine
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


if __name__ == "__main__":
    t_action_bar()
    t_fog()
    t_two_axis()
    t_delta()
    print("\n全部純邏輯煙霧測試通過 ✅（行動條/迷霧/兩軸/delta）")
