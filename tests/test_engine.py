"""单元测试：engine 纯逻辑（行动条 / 迷雾 / 两轴 / delta / TTL / 结构化日志）。

单元测试 = 只测单一函数，不碰网络/磁盘，最快也最多。每个 test_* 函数即一条测试，
用 assert 断言期望；夹具 `sess`（见 conftest.py）注入一份全新酒馆 Session。
"""
import pytest
from backend import engine, config
from backend.models import (
    Intent, Reaction, Condition, Adjudication, LedgerDelta, DeltaItem,
)


def test_action_bar_distribution(sess):
    """行动条：人人都能行动、玩家最活跃（速度最高）、玩家先手。"""
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
        sess.会变层.角色["scar"].特殊情况.append(Condition(内容="双手被反绑", 可见性="public"))
    intent = Intent(actor="player", 行动="攻击对方", 目标=target)
    assert engine.needs_reaction(sess, intent) == expected


# 轴B：是否争议（要不要掷运气）。被主动对抗、或环境本身是赌注 → 争议。
# ids= 给每组一个可读的报告名（否则中文会被转成难读的 \uXXXX）。
@pytest.mark.parametrize("action, react_target, expected", [
    ("掀桌撞他、全力攻击", "scar", True),    # 被对抗 → 争议
    ("后撤退两步",        None,   False),   # 平静后撤 → 非争议
    ("助跑跳过裂缝",      None,   True),    # 环境赌注（无对手仍争议）
], ids=["attacked-target", "calm-retreat", "risky-leap"])
def test_is_contested(sess, action, react_target, expected):
    intent = Intent(actor="player", 行动=action, 目标=None)
    assert engine.is_contested(sess, intent, react_target) is expected


def test_apply_delta(sess):
    """裁决 delta：状态新增与衍生栏（速度）更新生效。"""
    adj = Adjudication(
        结果阶梯="成功但有代价",
        ledger_delta=LedgerDelta(add=[
            DeltaItem(主体="scar", 类别="身心状况", 内容="右肩中刀",
                      gates="右手使不出重击", 可见性="public"),
        ]),
        速度更新={"scar": 3},
    )
    engine.apply_delta(sess, adj)
    blob = " ".join(c.内容 for c in sess.会变层.角色["scar"].身心状况)
    assert "右肩中刀" in blob
    assert sess.会变层.角色["scar"].行动速度 == 3


def test_ttl_expire(sess):
    """TTL：带剩余拍数的瞬态到期自动消失，持久状态（None）保留。"""
    sess.回合数 = 5
    engine.apply_delta(sess, Adjudication(ledger_delta=LedgerDelta(add=[
        DeltaItem(主体="scar", 类别="身心状况", 内容="被火光惊吓后退", 剩余拍数=2),
        DeltaItem(主体="scar", 类别="身心状况", 内容="右肋重伤"),  # 持久
    ])))  # 创建回合=5
    blob = lambda: " ".join(c.内容 for c in sess.会变层.角色["scar"].身心状况)
    sess.回合数 = 6
    engine.expire_transients(sess)
    assert "被火光惊吓后退" in blob()      # 差 1 拍，还在
    sess.回合数 = 7
    engine.expire_transients(sess)
    assert "被火光惊吓后退" not in blob()  # 差 2 拍，过期
    assert "右肋重伤" in blob()            # 持久不过期


def test_gender_in_views(sess):
    """角色信息：性别注入视图与地面真相，对手看得到（避免脑补性别）。"""
    view = engine.build_view(sess, "scar")     # 刀疤看阿青
    assert "阿青（我方，男）" in view
    assert "男" in engine.ground_truth(sess)


def test_log_entries_fog(sess):
    """结构化逐拍日志：总记行动者；开放行动连敌方也可见，反应文本仍仅我方。"""
    pi = Intent(actor="player", 行动="拔剑冲门", 目标="scar")
    e = engine.log_action_entry(sess, pi, None, "player", "你拔剑冲向门口。")
    assert e["行动者"] == "player"
    assert e["扮演"] == "玩家"               # 判定「玩家」靠扮演，不靠 id
    assert e["行动文本"] == "拔剑冲门"       # 我方：附输入

    ei = Intent(actor="scar", 行动="快刀直劈", 目标="player")   # 开放（隐蔽=False）
    pr = Reaction(actor="player", 反应="侧身格挡")
    e2 = engine.log_action_entry(sess, ei, pr, "scar", "刀疤挥刀。")
    assert e2["行动者"] == "scar"
    assert e2["扮演"] == "agent"            # 敌方 NPC 扮演=agent
    assert e2["行动文本"] == "快刀直劈"      # 敌方**开放**行动现在直接可见
    assert e2["反应文本"] == "侧身格挡"      # 我方反应可见（本轮反应轴不动）

    sys_e = engine.log_system_entry("【场景】酒馆")
    assert sys_e["行动者"] is None


def test_log_action_entry_hidden_surface(sess):
    """隐蔽行动的表象拆分（裁决后的正式条目）：
    敌方蒙混→显表象、被识破→显真意暴露、漏填表象→None（绝不漏真意）；我方隐蔽→真意（知底）。"""
    ei = Intent(actor="scar", 行动="使眼色给同伙递暗号", 目标=None, 隐蔽=True)

    # 蒙混过关：显裁决生成的表象，不显真意
    mix = engine.log_action_entry(sess, ei, None, "scar", "刀疤端起酒杯。",
                                  表象="端起酒杯抿了一口", 识破=False)
    assert mix["行动文本"] == "端起酒杯抿了一口"
    assert "暗号" not in mix["行动文本"]

    # 被识破：真意暴露
    seen = engine.log_action_entry(sess, ei, None, "scar", "阿青看穿了。",
                                   表象="", 识破=True)
    assert seen["行动文本"] == "使眼色给同伙递暗号"

    # LLM 漏填表象又没标识破：降级 None，绝不漏真意
    sloppy = engine.log_action_entry(sess, ei, None, "scar", "……",
                                     表象="", 识破=False)
    assert sloppy["行动文本"] is None

    # 我方隐蔽行动：玩家与其同阵营，看真意（知底）
    ally_hidden = Intent(actor="aqing", 行动="悄悄给玩家使眼色", 目标=None, 隐蔽=True)
    ah = engine.log_action_entry(sess, ally_hidden, None, "aqing", "阿青使了个眼色。",
                                 表象="", 识破=False)
    assert ah["行动文本"] == "悄悄给玩家使眼色"

    # 中立阵营也按「非我方」遮蔽（回归防护：别把判据误改成 阵营=="敌"，否则中立漏成可见）
    sess.角色卡["scar"].阵营 = "中立"
    neu = engine.log_action_entry(sess, ei, None, "scar", "……", 表象="凑近搭话", 识破=False)
    assert neu["行动文本"] == "凑近搭话" and "暗号" not in neu["行动文本"]


def test_log_action_entry_advance_flag(sess):
    """时间跳跃：推进非空 → 日志带描述供前端画分隔线；普通拍 → None。"""
    pi = Intent(actor="player", 行动="我很快买好回来了", 目标=None)
    jumped = engine.log_action_entry(sess, pi, None, "player", "半个时辰后，你拎着东西回来。",
                                     推进="半个时辰后你买好回来了")
    assert jumped["推进"] == "半个时辰后你买好回来了"
    normal = engine.log_action_entry(sess, pi, None, "player", "你站着没动。")
    assert normal["推进"] is None        # 默认空 → None，不画分隔线
    # 预告帧（log_pending_entry 走同闸门）也不带推进
    assert engine.log_pending_entry(sess, "player", pi)["推进"] is None


def test_log_pending_entry_fog(sess):
    """延迟遮盖的「进行中」预告帧（叙事未出、已裁决=False）：
    开放行动（含敌方）可提前显示；敌方**隐蔽**行动裁决前绝不预告。"""
    pi = Intent(actor="player", 行动="掀翻桌子撞他", 目标="scar")
    pe = engine.log_pending_entry(sess, "player", pi)
    assert pe["叙事"] is None and pe["行动文本"] == "掀翻桌子撞他"   # 我方意图可提前显示

    open_foe = Intent(actor="scar", 行动="挥刀直劈", 目标="player")  # 开放敌方
    of = engine.log_pending_entry(sess, "scar", open_foe)
    assert of["行动文本"] == "挥刀直劈"                              # 开放敌方行动也提前显示

    hidden_foe = Intent(actor="scar", 行动="偷偷拔刀", 目标="player", 隐蔽=True)
    hf = engine.log_pending_entry(sess, "scar", hidden_foe)
    assert hf["行动者"] == "scar" and hf["行动文本"] is None          # 敌方隐蔽意图不提前泄露

    r_ally = Reaction(actor="aqing", 反应="接住你抛来的刀")
    assert engine.log_pending_entry(sess, "player", pi, r_ally)["反应文本"] == "接住你抛来的刀"
    r_foe = Reaction(actor="scar", 反应="挥刀格开")
    assert engine.log_pending_entry(sess, "player", pi, r_foe)["反应文本"] is None  # 敌方回应不泄露（本轮）


def test_perception_brief_skips_unknown_keys(sess):
    """感知分发里 LLM 用了不存在的 key(角色名/虚构 id)时跳过、不崩(线上 KeyError 回归)。"""
    from backend import agents
    out = agents._perception_brief(sess, {"player": "全部", "凯尔": "无", "scar": "部分"})
    assert "凯尔" not in out                      # 未知 key 被跳过
    assert "玩家" in out and "刀疤" in out         # 有效 key 正常
    assert agents._perception_brief(sess, {"查无此人": "无"}) == "- 全体：全部"  # 全无效→默认


def test_resolve_id(sess):
    """agent 用名字，程序在边界解析回 id；兼容 id、未知→None。"""
    assert engine.resolve_id(sess, "scar") == "scar"     # 已是 id 原样
    assert engine.resolve_id(sess, "刀疤") == "scar"      # 名字→id
    assert engine.resolve_id(sess, "阿青") == "aqing"
    assert engine.resolve_id(sess, "查无此人") is None
    assert engine.resolve_id(sess, None) is None


def test_target_char_by_name(sess):
    """目标用名字也能解析到 id。"""
    assert engine.target_char(sess, Intent(actor="player", 行动="打", 目标="刀疤")) == "scar"
    assert engine.target_char(sess, Intent(actor="player", 行动="打", 目标="scar")) == "scar"
    assert engine.target_char(sess, Intent(actor="player", 行动="打", 目标="无此人")) is None


def test_apply_delta_keys_by_name(sess):
    """裁决用角色名当键（主体/速度更新/阵营变更）也能落到对应角色。"""
    adj = Adjudication(
        速度更新={"刀疤": 3},
        阵营变更={"刀疤": "我方"},
        ledger_delta=LedgerDelta(add=[DeltaItem(主体="刀疤", 类别="身心状况", 内容="右臂中刀")]),
    )
    engine.apply_delta(sess, adj)
    assert sess.会变层.角色["scar"].行动速度 == 3
    assert sess.角色卡["scar"].阵营 == "我方"
    assert any("右臂中刀" in c.内容 for c in sess.会变层.角色["scar"].身心状况)


def test_apply_delta_normalizes_self_visibility(sess):
    """裁决用名字写 self: 可见性 → 落账归一化为 self:id，自见才生效。"""
    adj = Adjudication(ledger_delta=LedgerDelta(add=[
        DeltaItem(主体="刀疤", 类别="身心状况", 内容="暗自怕火", 可见性="self:刀疤")]))
    engine.apply_delta(sess, adj)
    cond = sess.会变层.角色["scar"].身心状况[-1]
    assert cond.可见性 == "self:scar"                          # 名字→id
    assert engine._visible(cond, "scar", "敌") is True         # 本人可见
    assert engine._visible(cond, "player", "我方") is False    # 他人不可见


def test_distribute_private_by_name(sess):
    """私密叙事用角色名当键，也能分发到对应角色。"""
    engine.distribute(sess, "公开叙事", {"阿青": "阿青独有的感知"})
    assert sess.记忆["aqing"][-1] == "阿青独有的感知"
    assert sess.记忆["scar"][-1] == "公开叙事"


def test_player_id_by_role(sess):
    """玩家身份靠「扮演==玩家」识别，不依赖写死 id。"""
    assert engine.player_id(sess) == "player"      # tavern 玩家恰好 id=player
    sess.角色卡["player"].扮演 = "agent"
    sess.角色卡["aqing"].扮演 = "玩家"
    assert engine.player_id(sess) == "aqing"       # 改扮演后认 aqing，不看 id


def test_session_autofills_ledger_no_id_rewrite():
    """复现卡死剧本形状：玩家 id 非 'player' + 会变层.角色 为空 → 补局面、不改 id、可玩不卡死。"""
    from backend.models import Scenario, CharCard, Scene
    from backend import scenario as scen
    sc = Scenario(id="t", scene=Scene(id="s", 在场=["利拉特亚"]),
                  角色卡={"利拉特亚": CharCard(名="0", 阵营="我方", 扮演="玩家")})
    s = scen.session_from_scenario(sc)
    assert "利拉特亚" in s.角色卡 and "player" not in s.角色卡   # id 不被改写
    assert s.scene.在场 == ["利拉特亚"]
    assert "利拉特亚" in s.会变层.角色                          # 自动补了初始局面
    assert engine.player_id(s) == "利拉特亚"                    # 靠扮演识别玩家
    assert engine.pick_actor(s) == "利拉特亚"                   # 不卡死、识别为玩家


def test_pick_actor_empty_raises(sess):
    """会变层.角色 为空时立即报错，而非无限循环卡死。"""
    sess.会变层.角色 = {}
    with pytest.raises(ValueError):
        engine.pick_actor(sess)


def test_beats_to_act():
    """程序算好「还差几拍到门槛」：负初始行动值→很多拍后(模拟缓慢逼近)。"""
    from backend.models import CharLedger
    assert engine.beats_to_act(CharLedger(行动速度=5, 行动值=0)) == 4       # ceil(20/5)
    assert engine.beats_to_act(CharLedger(行动速度=5, 行动值=-40)) == 12    # ceil(60/5)
    assert engine.beats_to_act(CharLedger(行动速度=5, 行动值=20)) == 0      # 已到门槛
    assert engine.beats_to_act(CharLedger(行动速度=7, 行动值=0)) == 3       # ceil(20/7)


def test_action_order_slow_arriver_last(sess):
    """负初始行动值的角色(模拟缓慢逼近的援兵)排在行动次序最后、预估拍最大。"""
    sess.会变层.角色["scar"].行动值 = -40
    order = engine.action_order(sess)
    assert [t[0] for t in order][-1] == "scar"   # 慢的排最后
    assert order[-1][3] > order[0][3]            # 预估拍递增
    assert order[-1][3] >= 12                     # scar 约 12 拍后(缓慢逼近)


def test_faction_mates(sess):
    """同阵营互看（在场、排除自己）；跨阵营不含。"""
    assert engine.faction_mates(sess, "player") == ["aqing"]   # 我方队友(scar=敌不含)
    assert engine.faction_mates(sess, "scar") == []            # 敌方仅一人


def test_apply_delta_faction_change(sess):
    """裁决的阵营变更就地改角色卡阵营（倒戈/投靠），影响同阵营判定。"""
    assert sess.角色卡["scar"].阵营 == "敌"
    engine.apply_delta(sess, Adjudication(阵营变更={"scar": "我方"}))
    assert sess.角色卡["scar"].阵营 == "我方"
    assert "scar" in engine.faction_mates(sess, "player")      # 倒戈后成我方队友


def test_mates_brief_full_card_same_faction_only(sess):
    """同阵营队友卡含弱点；跨阵营不泄露。"""
    from backend import agents
    engine.apply_delta(sess, Adjudication(阵营变更={"scar": "我方"}))
    brief = agents._mates_brief(sess, "player")
    assert "刀疤" in brief and "怕火" in brief                  # 我方队友给整张卡(含弱点)
    engine.apply_delta(sess, Adjudication(阵营变更={"scar": "敌"}))
    assert "怕火" not in agents._mates_brief(sess, "player")    # 敌方资料不泄露


def test_remove_skips_empty_key(sess):
    """remove 里若混入空串，须跳过而非清空整列（"" in 内容 恒真的陷阱）；真关键字照常移除。"""
    cl = sess.会变层.角色["scar"]
    cl.身心状况 = [Condition(内容="右臂中刀"), Condition(内容="面色发白")]
    engine.apply_delta(sess, Adjudication(ledger_delta=LedgerDelta(remove=["", "右臂中刀"])))
    blobs = {c.内容 for c in cl.身心状况}
    assert "右臂中刀" not in blobs        # 真关键字正常移除
    assert "面色发白" in blobs            # 空串没把整列清掉
