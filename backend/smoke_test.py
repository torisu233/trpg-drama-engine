"""纯逻辑烟雾测试（不需 Grok API）。
验证：行动条节奏、迷雾过滤、两轴判定、delta 套用。

运行：  python -m backend.smoke_test
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
    assert all(v > 0 for v in counts.values()), f"有人挨饿: {counts}"
    assert counts["player"] >= counts["aqing"], f"玩家应最活跃: {counts}"
    assert seq[0] == "player", f"玩家应先手: {seq[:3]}"
    print(f"[行动条] 30 拍分布 {counts} 前八拍 {seq[:8]}  ✓")


def t_fog():
    s = new_tavern_session()
    view = engine.build_view(s, "player")
    assert "怕火" not in view, "玩家不该看到 gm 秘密(怕火)"
    assert "等同伙" not in view, "玩家不该看到 gm 秘密(包抄)"
    assert "后门上锁" in view, "玩家应看到公开事实"
    assert "短刃" in view, "玩家应看到自己的物品"
    gt = engine.ground_truth(s)
    assert "怕火" in gt and "等同伙" in gt, "裁决的地面真相应含 gm 秘密"
    print("[迷雾] 玩家视图隐藏 gm 秘密、裁决可见全貌  ✓")


def t_two_axis():
    s = new_tavern_session()
    # 攻击清醒的敌人 → 收反应 + 争议
    atk = Intent(actor="player", 行动="掀桌撞他、全力攻击", 目标="scar")
    assert engine.needs_reaction(s, atk) == "scar", "攻击清醒敌人应收反应"
    assert engine.is_contested(s, atk, "scar") is True, "攻击应为争议"

    # 攻击被绑的敌人 → 不收反应
    s.会变层.角色["scar"].特殊情况.append(Condition(内容="双手被反绑", 可见性="public"))
    assert engine.needs_reaction(s, atk) is None, "被绑者无法反应，不应收反应"

    # 无对象后撤 → 不收反应、非争议
    retreat = Intent(actor="player", 行动="后撤退两步", 目标=None)
    assert engine.needs_reaction(s, retreat) is None
    assert engine.is_contested(s, retreat, None) is False, "平静后撤非争议"

    # 环境赌注（无对手仍争议）
    leap = Intent(actor="player", 行动="助跑跳过裂缝", 目标=None)
    assert engine.is_contested(s, leap, None) is True, "跳跃应为环境争议"
    print("[两轴] 反应收集 / 争议判定 全部符合预期  ✓")


def t_delta():
    s = new_tavern_session()
    adj = Adjudication(
        结果阶梯="成功但有代价",
        ledger_delta=LedgerDelta(add=[
            DeltaItem(主体="scar", 类别="身心状况", 内容="右肩中刀",
                      gates="右手使不出重击", 可见性="public"),
        ]),
        速度更新={"scar": 3},
    )
    engine.apply_delta(s, adj)
    blob = " ".join(c.内容 for c in s.会变层.角色["scar"].身心状况)
    assert "右肩中刀" in blob, "delta add 应生效"
    assert s.会变层.角色["scar"].行动速度 == 3, "速度更新应生效"
    print("[delta] 状态增删与衍生栏更新生效  ✓")


def t_expire():
    s = new_tavern_session()
    s.回合数 = 5
    engine.apply_delta(s, Adjudication(ledger_delta=LedgerDelta(add=[
        DeltaItem(主体="scar", 类别="身心状况", 内容="被火光惊吓后退", 剩余拍数=2),
        DeltaItem(主体="scar", 类别="身心状况", 内容="右肋重伤"),   # 剩余拍数 None = 持久
    ])))  # 创建回合=5
    blob = lambda: " ".join(c.内容 for c in s.会变层.角色["scar"].身心状况)
    s.回合数 = 6; engine.expire_transients(s)
    assert "被火光惊吓后退" in blob(), "剩余2拍，第6回合(差1)应还在"
    s.回合数 = 7; engine.expire_transients(s)
    assert "被火光惊吓后退" not in blob(), "剩余2拍，第7回合(差2)应过期"
    assert "右肋重伤" in blob(), "持久状态(None)不该过期"
    print("[TTL] 瞬态自动过期、持久状态保留  ✓")


async def _t_compress():
    s = new_tavern_session()
    s.记忆["scar"] = [f"第{i}拍叙事" for i in range(1, 13)]   # 12 条
    async def fake_sum(grok, sess, cid, old, evicted):       # 替身，避免打 API
        return f"[摘要:并入{len(evicted)}条]"
    orig, agents.summarize_memory = agents.summarize_memory, fake_sum
    try:
        await flow._maybe_compress(None, s)
    finally:
        agents.summarize_memory = orig
    assert len(s.记忆["scar"]) == 7, f"12 条应折出 5 剩 7：{len(s.记忆['scar'])}"
    assert s.记忆["scar"][0] == "第6拍叙事", "保留的应是较新的 5~9 条"
    assert s.摘要.get("scar"), "应产生摘要"
    print(f"[摘要] scar 记忆 12→{len(s.记忆['scar'])} 条 + 生成摘要（evict 最旧 {config.KEEP_RECENT} 条）  ✓")


def t_compress():
    asyncio.run(_t_compress())


def t_gender():
    s = new_tavern_session()
    view = engine.build_view(s, "scar")          # 刀疤看阿青
    assert "阿青（我方，男）" in view, f"对手视图应含性别: {view}"
    assert "男" in engine.ground_truth(s), "地面真相应含性别"
    print("[角色信息] 性别已注入视图/地面真相，对手看得到  ✓")


async def _t_consolidate():
    s = new_tavern_session()
    # 5 条公开持久近义 + 1 gm；身心状况放 1 条 TTL 瞬态
    s.会变层.场景.社会事实 = [Condition(内容=f"刀疤要求先还债#{i}", 可见性="public") for i in range(5)]
    s.会变层.场景.社会事实.append(Condition(内容="刀疤在等同伙", 可见性="gm"))
    s.会变层.角色["player"].身心状况 = [Condition(内容="瞬态晕眩", 可见性="public", 剩余拍数=2)]

    async def fake(grok, sess, label, conds):
        return [Condition(内容="刀疤要求先清漕帮债务（合并）", 可见性="public", 来源="整理")]
    orig, agents.consolidate_conditions = agents.consolidate_conditions, fake
    try:
        await flow._maybe_consolidate(None, s)
    finally:
        agents.consolidate_conditions = orig

    社 = [c.内容 for c in s.会变层.场景.社会事实]
    assert "刀疤要求先清漕帮债务（合并）" in 社, "公开持久近义应被合并"
    assert "刀疤在等同伙" in 社, "gm 条目不可被整理动到"
    assert len(s.会变层.场景.社会事实) == 2, f"6→2（合并1+保留gm1）：实得 {len(社)}"
    assert len(s.会变层.角色["player"].身心状况) == 1, "带 TTL 的瞬态不应被整理"
    print(f"[帐本整理] 社会事实 6→{len(社)}（公开持久合并、gm/瞬态保留）  ✓")


def t_consolidate():
    asyncio.run(_t_consolidate())


def t_scenario():
    import json as _json
    from .models import Scenario
    from . import scenario as scen
    s0 = new_tavern_session()
    sc = scen.scenario_from_session(s0, "tavern")
    # JSON 来回不掉数据
    sc2 = Scenario(**_json.loads(sc.model_dump_json()))
    s1 = scen.session_from_scenario(sc2)
    assert "怕火" in "".join(s1.角色卡["scar"].弱点), "角色卡弱点(怕火)应保留"
    assert s1.角色卡["aqing"].性别 == "男", "性别应保留"
    assert any("等同伙" in c.内容 for c in s1.会变层.场景.场景事实), "gm 秘密应保留"
    assert s1.会变层.角色["player"].行动速度 == config.SPEED_PLAYER, "行动速度应保留"
    assert s1.世界观.法则, "世界观法则应保留"
    # session 运行期字段正确初始化
    assert s1.回合数 == 0 and s1.pending is None
    assert set(s1.记忆.keys()) == set(s1.scene.在场), "记忆键=在场名单"
    assert any("开场" in line for line in s1.公开日志), "公开日志含开场"
    print("[剧本] Scenario 访问/转换来回无损，session 初始化正确  ✓")


def t_author_merge():
    from .models import Scenario, AuthorReply, World, CharCard, Ledger, CharLedger
    from . import scenario as scen
    sc = Scenario(
        id="t",
        世界观=World(基调="武侠", 背景="边城", 法则=["法则A"]),
        角色卡={"scar": CharCard(名="刀疤", 阵营="敌", 能力=["快刀"], 弱点=["怕火"])},
    )
    # 改 world：只加法则，基调/背景留空 → 不该被清
    scen.apply_author_reply(sc, AuthorReply(reply="", 区块="world",
        world=World(基调="", 背景="", 法则=["法则A", "法则B"])))
    assert sc.世界观.基调 == "武侠" and sc.世界观.背景 == "边城", "空栏不该清掉既有"
    assert sc.世界观.法则 == ["法则A", "法则B"]
    # 改 char：只改弱点，能力留空 → 能力不该被清
    scen.apply_author_reply(sc, AuthorReply(reply="", 区块="char", char_id="scar",
        char=CharCard(名="刀疤", 阵营="敌", 弱点=["怕火", "怕水"])))
    assert sc.角色卡["scar"].能力 == ["快刀"], "char 其他栏不该被清"
    assert sc.角色卡["scar"].弱点 == ["怕火", "怕水"]
    # ledger：添加 player 局面，不该清掉既有 scar 局面
    sc.会变层.角色["scar"] = CharLedger(姿势位置="门口")
    scen.apply_author_reply(sc, AuthorReply(reply="", 区块="ledger",
        ledger=Ledger(角色={"player": CharLedger(姿势位置="桌边")})))
    assert "scar" in sc.会变层.角色 and "player" in sc.会变层.角色, "ledger 角色应 key 级合并"
    print("[编剧合并] 空栏不误清、char 保留其他栏、ledger 角色 key 级保留  ✓")


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
    print("\n全部纯逻辑烟雾测试通过 ✅（…/剧本/编剧合并）")
