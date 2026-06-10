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
    atk = Intent(actor="player", 行動="掀桌撞他、全力攻擊", 目標="scar")
    assert engine.needs_reaction(s, atk) == "scar", "攻擊清醒敵人應收反應"
    assert engine.is_contested(s, atk, "scar") is True, "攻擊應為爭議"

    # 攻擊被綁的敵人 → 不收反應
    s.會變層.角色["scar"].特殊情況.append(Condition(內容="雙手被反綁", 可見性="public"))
    assert engine.needs_reaction(s, atk) is None, "被綁者無法反應，不應收反應"

    # 無對象後撤 → 不收反應、非爭議
    retreat = Intent(actor="player", 行動="後撤退兩步", 目標=None)
    assert engine.needs_reaction(s, retreat) is None
    assert engine.is_contested(s, retreat, None) is False, "平靜後撤非爭議"

    # 環境賭注（無對手仍爭議）
    leap = Intent(actor="player", 行動="助跑跳過裂縫", 目標=None)
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


def t_gender():
    s = new_tavern_session()
    view = engine.build_view(s, "scar")          # 刀疤看阿青
    assert "阿青（我方，男）" in view, f"對手視圖應含性別: {view}"
    assert "男" in engine.ground_truth(s), "地面真相應含性別"
    print("[角色資訊] 性別已注入視圖/地面真相，對手看得到  ✓")


async def _t_consolidate():
    s = new_tavern_session()
    # 5 條公開持久近義 + 1 gm；身心狀況放 1 條 TTL 瞬態
    s.會變層.場景.社會事實 = [Condition(內容=f"刀疤要求先還債#{i}", 可見性="public") for i in range(5)]
    s.會變層.場景.社會事實.append(Condition(內容="刀疤在等同夥", 可見性="gm"))
    s.會變層.角色["player"].身心狀況 = [Condition(內容="瞬態暈眩", 可見性="public", 剩餘拍數=2)]

    async def fake(grok, sess, label, conds):
        return [Condition(內容="刀疤要求先清漕幫債務（合併）", 可見性="public", 來源="整理")]
    orig, agents.consolidate_conditions = agents.consolidate_conditions, fake
    try:
        await flow._maybe_consolidate(None, s)
    finally:
        agents.consolidate_conditions = orig

    社 = [c.內容 for c in s.會變層.場景.社會事實]
    assert "刀疤要求先清漕幫債務（合併）" in 社, "公開持久近義應被合併"
    assert "刀疤在等同夥" in 社, "gm 條目不可被整理動到"
    assert len(s.會變層.場景.社會事實) == 2, f"6→2（合併1+保留gm1）：實得 {len(社)}"
    assert len(s.會變層.角色["player"].身心狀況) == 1, "帶 TTL 的瞬態不應被整理"
    print(f"[帳本整理] 社會事實 6→{len(社)}（公開持久合併、gm/瞬態保留）  ✓")


def t_consolidate():
    asyncio.run(_t_consolidate())


def t_scenario():
    import json as _json
    from .models import Scenario
    from . import scenario as scen
    s0 = new_tavern_session()
    sc = scen.scenario_from_session(s0, "tavern")
    # JSON 來回不掉資料
    sc2 = Scenario(**_json.loads(sc.model_dump_json()))
    s1 = scen.session_from_scenario(sc2)
    assert "怕火" in "".join(s1.角色卡["scar"].弱點), "角色卡弱點(怕火)應保留"
    assert s1.角色卡["aqing"].性別 == "男", "性別應保留"
    assert any("等同夥" in c.內容 for c in s1.會變層.場景.場景事實), "gm 秘密應保留"
    assert s1.會變層.角色["player"].行動速度 == config.SPEED_PLAYER, "行動速度應保留"
    assert s1.世界觀.法則, "世界觀法則應保留"
    # session 執行期欄位正確初始化
    assert s1.回合數 == 0 and s1.pending is None
    assert set(s1.記憶.keys()) == set(s1.scene.在場), "記憶鍵=在場名單"
    assert any("開場" in line for line in s1.公開日誌), "公開日誌含開場"
    print("[劇本] Scenario 存取/轉換來回無損，session 初始化正確  ✓")


def t_author_merge():
    from .models import Scenario, AuthorReply, World, CharCard, Ledger, CharLedger
    from . import scenario as scen
    sc = Scenario(
        id="t",
        世界觀=World(基調="武俠", 背景="邊城", 法則=["法則A"]),
        角色卡={"scar": CharCard(名="刀疤", 陣營="敵", 能力=["快刀"], 弱點=["怕火"])},
    )
    # 改 world：只加法則，基調/背景留空 → 不該被清
    scen.apply_author_reply(sc, AuthorReply(reply="", 區塊="world",
        world=World(基調="", 背景="", 法則=["法則A", "法則B"])))
    assert sc.世界觀.基調 == "武俠" and sc.世界觀.背景 == "邊城", "空欄不該清掉既有"
    assert sc.世界觀.法則 == ["法則A", "法則B"]
    # 改 char：只改弱點，能力留空 → 能力不該被清
    scen.apply_author_reply(sc, AuthorReply(reply="", 區塊="char", char_id="scar",
        char=CharCard(名="刀疤", 陣營="敵", 弱點=["怕火", "怕水"])))
    assert sc.角色卡["scar"].能力 == ["快刀"], "char 其他欄不該被清"
    assert sc.角色卡["scar"].弱點 == ["怕火", "怕水"]
    # ledger：新增 player 局面，不該清掉既有 scar 局面
    sc.會變層.角色["scar"] = CharLedger(姿勢位置="門口")
    scen.apply_author_reply(sc, AuthorReply(reply="", 區塊="ledger",
        ledger=Ledger(角色={"player": CharLedger(姿勢位置="桌邊")})))
    assert "scar" in sc.會變層.角色 and "player" in sc.會變層.角色, "ledger 角色應 key 級合併"
    print("[編劇合併] 空欄不誤清、char 保留其他欄、ledger 角色 key 級保留  ✓")


if __name__ == "__main__":
    t_action_bar()
    t_fog()
    t_two_axis()
    t_delta()
    t_expire()
    t_compress()
    t_gender()
    t_consolidate()
    t_scenario()
    t_author_merge()
    print("\n全部純邏輯煙霧測試通過 ✅（…/劇本/編劇合併）")
