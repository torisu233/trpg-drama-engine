"""单元测试：engine 纯逻辑（action_bar / 迷雾 / 两轴 / delta / TTL / 结构化日志）。

单元测试 = 只测单一函数，不碰网络/磁盘，最快也最多。每个 test_* 函数即一条测试，
用 assert 断言期望；夹具 `sess`（见 conftest.py）注入一份全新酒馆 Session。
"""
import pytest
from backend import engine, config
from backend.models import (
    Intent, Reaction, Condition, Adjudication, LedgerDelta, DeltaItem,
)


def test_action_bar_distribution(sess):
    """action_bar：人人都能行动、玩家最活跃（速度最高）、玩家先手。"""
    counts = {"player": 0, "aqing": 0, "scar": 0}
    seq = []
    for _ in range(30):
        actor = engine.pick_actor(sess)
        counts[actor] += 1
        seq.append(actor)
        engine.consume_turn(sess, actor)
    assert all(v > 0 for v in counts.values()), f"有人挨饿: {counts}"
    assert counts["player"] >= counts["aqing"], f"玩家应最活跃: {counts}"
    assert seq[0] == "player", f"玩家应先手: {seq[:3]}"


def test_fog_hides_gm_secrets(sess):
    """迷雾：玩家视图隐藏 gm 秘密，裁决的地面真相可见全貌。"""
    view = engine.build_view(sess, "player")
    assert "怕火" not in view
    assert "等同伙" not in view
    assert "后门上锁" in view          # 公开事实可见
    assert "短刃" in view              # 自己的物品可见
    gt = engine.ground_truth(sess)
    assert "怕火" in gt and "等同伙" in gt


# 轴A：该不该向目标收反应。bound=是否把 scar 绑住（绑住就无法反应）。
@pytest.mark.parametrize("bound, target, expected", [
    (False, "scar", "scar"),   # 清醒的敌人 → 该收反应
    (True,  "scar", None),     # 被绑无法反应 → 不收
    (False, None,   None),     # 没有对象 → 不收
])
def test_needs_reaction(sess, bound, target, expected):
    if bound:
        sess.ledger.characters["scar"].status_effects.append(Condition(content="双手被反绑", visibility="public"))
    intent = Intent(actor="player", action="攻击对方", target=target)
    assert engine.needs_reaction(sess, intent) == expected


# 轴B：是否争议（要不要掷运气）。被主动对抗、或环境本身是赌注 → 争议。
# ids= 给每组一个可读的报告名（否则中文会被转成难读的 \uXXXX）。
@pytest.mark.parametrize("action, react_target, expected", [
    ("掀桌撞他、全力攻击", "scar", True),    # 被对抗 → 争议
    ("后撤退两步",        None,   False),   # 平静后撤 → 非争议
    ("助跑跳过裂缝",      None,   True),    # 环境赌注（无对手仍争议）
], ids=["attacked-target", "calm-retreat", "risky-leap"])
def test_is_contested(sess, action, react_target, expected):
    intent = Intent(actor="player", action=action, target=None)
    assert engine.is_contested(sess, intent, react_target) is expected


def test_apply_delta(sess):
    """adjudication delta：状态新增与衍生栏（速度）更新生效。"""
    adj = Adjudication(
        outcome="success_with_cost",
        ledger_delta=LedgerDelta(add=[
            DeltaItem(subject="scar", category="conditions", content="右肩中刀",
                      gates="右手使不出重击", visibility="public"),
        ]),
        speed_updates={"scar": 3},
    )
    engine.apply_delta(sess, adj)
    blob = " ".join(c.content for c in sess.ledger.characters["scar"].conditions)
    assert "右肩中刀" in blob
    assert sess.ledger.characters["scar"].speed == 3


def test_ttl_expire(sess):
    """TTL：带剩余拍数的瞬态到期自动消失，持久状态（None）保留。"""
    sess.turn = 5
    engine.apply_delta(sess, Adjudication(ledger_delta=LedgerDelta(add=[
        DeltaItem(subject="scar", category="conditions", content="被火光惊吓后退", ttl=2),
        DeltaItem(subject="scar", category="conditions", content="右肋重伤"),  # 持久
    ])))  # created_turn=5
    blob = lambda: " ".join(c.content for c in sess.ledger.characters["scar"].conditions)
    sess.turn = 6
    engine.expire_transients(sess)
    assert "被火光惊吓后退" in blob()      # 差 1 拍，还在
    sess.turn = 7
    engine.expire_transients(sess)
    assert "被火光惊吓后退" not in blob()  # 差 2 拍，过期
    assert "右肋重伤" in blob()            # 持久不过期


def test_gender_in_views(sess):
    """角色信息：性别注入视图与地面真相，对手看得到（避免脑补性别）。"""
    view = engine.build_view(sess, "scar")     # 刀疤看阿青
    assert "阿青（ally，男）" in view
    assert "男" in engine.ground_truth(sess)


def test_log_entries_fog(sess):
    """结构化逐拍日志：总记行动者；开放行动连敌方也可见，反应文本仍仅我方。"""
    pi = Intent(actor="player", action="拔剑冲门", target="scar")
    e = engine.log_action_entry(sess, pi, None, "player", "你拔剑冲向门口。")
    assert e["actor"] == "player"
    assert e["controller"] == "player"               # 判定「player」靠扮演，不靠 id
    assert e["action_text"] == "拔剑冲门"       # ally：附输入

    ei = Intent(actor="scar", action="快刀直劈", target="player")   # 开放（covert=False）
    pr = Reaction(actor="player", reaction="侧身格挡")
    e2 = engine.log_action_entry(sess, ei, pr, "scar", "刀疤挥刀。")
    assert e2["actor"] == "scar"
    assert e2["controller"] == "agent"            # 敌方 NPC controller=agent
    assert e2["action_text"] == "快刀直劈"      # 敌方**开放**行动现在直接可见
    assert e2["reaction_text"] == "侧身格挡"      # 我方反应可见（本轮反应轴不动）

    sys_e = engine.log_system_entry("【scene】酒馆")
    assert sys_e["actor"] is None


def test_log_action_entry_hidden_surface(sess):
    """隐蔽行动的表象拆分（裁决后的正式条目）：
    敌方蒙混→显表象、被识破→显真意暴露、漏填表象→None（绝不漏真意）；我方隐蔽→真意（知底）。"""
    ei = Intent(actor="scar", action="使眼色给同伙递暗号", target=None, covert=True)

    # 蒙混过关：显裁决生成的表象，不显真意
    mix = engine.log_action_entry(sess, ei, None, "scar", "刀疤端起酒杯。",
                                  cover="端起酒杯抿了一口", detected=False)
    assert mix["action_text"] == "端起酒杯抿了一口"
    assert "暗号" not in mix["action_text"]

    # 被识破：真意暴露
    seen = engine.log_action_entry(sess, ei, None, "scar", "阿青看穿了。",
                                   cover="", detected=True)
    assert seen["action_text"] == "使眼色给同伙递暗号"

    # LLM 漏填表象又没标识破：降级 None，绝不漏真意
    sloppy = engine.log_action_entry(sess, ei, None, "scar", "……",
                                     cover="", detected=False)
    assert sloppy["action_text"] is None

    # 我方隐蔽行动：玩家与其同阵营，看真意（知底）
    ally_hidden = Intent(actor="aqing", action="悄悄给玩家使眼色", target=None, covert=True)
    ah = engine.log_action_entry(sess, ally_hidden, None, "aqing", "阿青使了个眼色。",
                                 cover="", detected=False)
    assert ah["action_text"] == "悄悄给玩家使眼色"

    # 中立阵营也按「非我方」遮蔽（回归防护：别把判据误改成 faction=="enemy"，否则中立漏成可见）
    sess.cards["scar"].faction = "neutral"
    neu = engine.log_action_entry(sess, ei, None, "scar", "……", cover="凑近搭话", detected=False)
    assert neu["action_text"] == "凑近搭话" and "暗号" not in neu["action_text"]


def test_log_action_entry_advance_flag(sess):
    """时间跳跃：推进非空 → 日志带描述供前端画分隔线；普通拍 → None。"""
    pi = Intent(actor="player", action="我很快买好回来了", target=None)
    jumped = engine.log_action_entry(sess, pi, None, "player", "半个时辰后，你拎着东西回来。",
                                     time_skip="半个时辰后你买好回来了")
    assert jumped["time_skip"] == "半个时辰后你买好回来了"
    normal = engine.log_action_entry(sess, pi, None, "player", "你站着没动。")
    assert normal["time_skip"] is None        # 默认空 → None，不画分隔线
    # 预告帧（log_pending_entry 走同闸门）也不带推进
    assert engine.log_pending_entry(sess, "player", pi)["time_skip"] is None


def test_log_pending_entry_fog(sess):
    """延迟遮盖的「in_progress」预告帧（叙事未出、resolved=False）：
    开放行动（含敌方）可提前显示；敌方**covert**行动裁决前绝不预告。"""
    pi = Intent(actor="player", action="掀翻桌子撞他", target="scar")
    pe = engine.log_pending_entry(sess, "player", pi)
    assert pe["narration"] is None and pe["action_text"] == "掀翻桌子撞他"   # 我方意图可提前显示

    open_foe = Intent(actor="scar", action="挥刀直劈", target="player")  # 开放敌方
    of = engine.log_pending_entry(sess, "scar", open_foe)
    assert of["action_text"] == "挥刀直劈"                              # 开放敌方行动也提前显示

    hidden_foe = Intent(actor="scar", action="偷偷拔刀", target="player", covert=True)
    hf = engine.log_pending_entry(sess, "scar", hidden_foe)
    assert hf["actor"] == "scar" and hf["action_text"] is None          # 敌方隐蔽意图不提前泄露

    r_ally = Reaction(actor="aqing", reaction="接住你抛来的刀")
    assert engine.log_pending_entry(sess, "player", pi, r_ally)["reaction_text"] == "接住你抛来的刀"
    r_foe = Reaction(actor="scar", reaction="挥刀格开")
    assert engine.log_pending_entry(sess, "player", pi, r_foe)["reaction_text"] is None  # 敌方回应不泄露（本轮）


def test_perception_brief_skips_unknown_keys(sess):
    """感知分发里 LLM 用了不存在的 key(角色名/虚构 id)时跳过、不崩(线上 KeyError 回归)。"""
    from backend import agents
    out = agents._perception_brief(sess, {"player": "all", "凯尔": "none", "scar": "partial"})
    assert "凯尔" not in out                      # 未知 key 被跳过
    assert "player" in out and "刀疤" in out         # 有效 key normal
    assert agents._perception_brief(sess, {"查无此人": "none"}) == "- 全体：all"  # 全无效→默认


def test_resolve_id(sess):
    """agent 用名字，程序在边界解析回 id；兼容 id、未知→None。"""
    assert engine.resolve_id(sess, "scar") == "scar"     # 已是 id 原样
    assert engine.resolve_id(sess, "刀疤") == "scar"      # 名字→id
    assert engine.resolve_id(sess, "阿青") == "aqing"
    assert engine.resolve_id(sess, "查无此人") is None
    assert engine.resolve_id(sess, None) is None


def test_target_char_by_name(sess):
    """目标用名字也能解析到 id。"""
    assert engine.target_char(sess, Intent(actor="player", action="打", target="刀疤")) == "scar"
    assert engine.target_char(sess, Intent(actor="player", action="打", target="scar")) == "scar"
    assert engine.target_char(sess, Intent(actor="player", action="打", target="无此人")) is None


def test_apply_delta_keys_by_name(sess):
    """裁决用角色名当键（subject/speed_updates/faction_changes）也能落到对应角色。"""
    adj = Adjudication(
        speed_updates={"刀疤": 3},
        faction_changes={"刀疤": "ally"},
        ledger_delta=LedgerDelta(add=[DeltaItem(subject="刀疤", category="conditions", content="右臂中刀")]),
    )
    engine.apply_delta(sess, adj)
    assert sess.ledger.characters["scar"].speed == 3
    assert sess.cards["scar"].faction == "ally"
    assert any("右臂中刀" in c.content for c in sess.ledger.characters["scar"].conditions)


def test_apply_delta_normalizes_self_visibility(sess):
    """裁决用名字写 self: visibility → 落账归一化为 self:id，自见才生效。"""
    adj = Adjudication(ledger_delta=LedgerDelta(add=[
        DeltaItem(subject="刀疤", category="conditions", content="暗自怕火", visibility="self:刀疤")]))
    engine.apply_delta(sess, adj)
    cond = sess.ledger.characters["scar"].conditions[-1]
    assert cond.visibility == "self:scar"                          # 名字→id
    assert engine._visible(cond, "scar", "enemy") is True         # 本人可见
    assert engine._visible(cond, "player", "ally") is False    # 他人不可见


def test_distribute_private_by_name(sess):
    """私密叙事用角色名当键，也能分发到对应角色。"""
    engine.distribute(sess, "公开叙事", {"阿青": "阿青独有的感知"})
    assert sess.memory["aqing"][-1] == "阿青独有的感知"
    assert sess.memory["scar"][-1] == "公开叙事"


def test_player_id_by_role(sess):
    """玩家身份靠「controller==player」识别，不依赖写死 id。"""
    assert engine.player_id(sess) == "player"      # tavern 玩家恰好 id=player
    sess.cards["player"].controller = "agent"
    sess.cards["aqing"].controller = "player"
    assert engine.player_id(sess) == "aqing"       # 改扮演后认 aqing，不看 id


def test_session_autofills_ledger_no_id_rewrite():
    """复现卡死剧本形状：player id 非 'player' + ledger.characters 为空 → 补局面、不改 id、可玩不卡死。"""
    from backend.models import Scenario, CharCard, Scene
    from backend import scenario as scen
    sc = Scenario(id="t", scene=Scene(id="s", present=["利拉特亚"]),
                  cards={"利拉特亚": CharCard(name="0", faction="ally", controller="player")})
    s = scen.session_from_scenario(sc)
    assert "利拉特亚" in s.cards and "player" not in s.cards   # id 不被改写
    assert s.scene.present == ["利拉特亚"]
    assert "利拉特亚" in s.ledger.characters                          # 自动补了初始局面
    assert engine.player_id(s) == "利拉特亚"                    # 靠扮演识别玩家
    assert engine.pick_actor(s) == "利拉特亚"                   # 不卡死、识别为玩家


def test_pick_actor_empty_raises(sess):
    """ledger.characters 为空时立即报错，而非无限循环卡死。"""
    sess.ledger.characters = {}
    with pytest.raises(ValueError):
        engine.pick_actor(sess)


def test_beats_to_act():
    """程序算好「还差几拍到门槛」：负初始行动值→很多拍后(模拟缓慢逼近)。"""
    from backend.models import CharLedger
    assert engine.beats_to_act(CharLedger(speed=5, gauge=0)) == 4       # ceil(20/5)
    assert engine.beats_to_act(CharLedger(speed=5, gauge=-40)) == 12    # ceil(60/5)
    assert engine.beats_to_act(CharLedger(speed=5, gauge=20)) == 0      # 已到门槛
    assert engine.beats_to_act(CharLedger(speed=7, gauge=0)) == 3       # ceil(20/7)


def test_action_order_slow_arriver_last(sess):
    """负初始行动值的角色(模拟缓慢逼近的援兵)排在行动次序最后、预估拍最大。"""
    sess.ledger.characters["scar"].gauge = -40
    order = engine.action_order(sess)
    assert [t[0] for t in order][-1] == "scar"   # 慢的排最后
    assert order[-1][3] > order[0][3]            # 预估拍递增
    assert order[-1][3] >= 12                     # scar 约 12 拍后(缓慢逼近)


def test_faction_mates(sess):
    """同阵营互看（present、排除自己）；跨阵营不含。"""
    assert engine.faction_mates(sess, "player") == ["aqing"]   # 我方队友(scar=敌不含)
    assert engine.faction_mates(sess, "scar") == []            # 敌方仅一人


def test_apply_delta_faction_change(sess):
    """裁决的阵营变更就地改角色卡阵营（倒戈/投靠），影响同阵营判定。"""
    assert sess.cards["scar"].faction == "enemy"
    engine.apply_delta(sess, Adjudication(faction_changes={"scar": "ally"}))
    assert sess.cards["scar"].faction == "ally"
    assert "scar" in engine.faction_mates(sess, "player")      # 倒戈后成我方队友


def test_mates_brief_full_card_same_faction_only(sess):
    """同阵营队友卡含弱点；跨阵营不泄露。"""
    from backend import agents
    engine.apply_delta(sess, Adjudication(faction_changes={"scar": "ally"}))
    brief = agents._mates_brief(sess, "player")
    assert "刀疤" in brief and "怕火" in brief                  # 我方队友给整张卡(含弱点)
    engine.apply_delta(sess, Adjudication(faction_changes={"scar": "enemy"}))
    assert "怕火" not in agents._mates_brief(sess, "player")    # 敌方资料不泄露


def test_remove_skips_empty_key(sess):
    """remove 里若混入空串，须跳过而非清空整列（"" in content 恒真的陷阱）；真关键字照常移除。"""
    cl = sess.ledger.characters["scar"]
    cl.conditions = [Condition(content="右臂中刀"), Condition(content="面色发白")]
    engine.apply_delta(sess, Adjudication(ledger_delta=LedgerDelta(remove=["", "右臂中刀"])))
    blobs = {c.content for c in cl.conditions}
    assert "右臂中刀" not in blobs        # 真关键字正常移除
    assert "面色发白" in blobs            # 空串没把整列清掉
