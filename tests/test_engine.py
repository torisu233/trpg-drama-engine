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
    """结构化逐拍日志：总记行动者；我方附输入文本，敌方意图不外泄。"""
    pi = Intent(actor="player", 行动="拔剑冲门", 目标="scar")
    e = engine.log_action_entry(sess, pi, None, "player", "你拔剑冲向门口。")
    assert e["行动者"] == "player"
    assert e["扮演"] == "玩家"               # 判定「玩家」靠扮演，不靠 id
    assert e["行动文本"] == "拔剑冲门"       # 我方：附输入

    ei = Intent(actor="scar", 行动="快刀直劈", 目标="player")
    pr = Reaction(actor="player", 反应="侧身格挡")
    e2 = engine.log_action_entry(sess, ei, pr, "scar", "刀疤挥刀。")
    assert e2["行动者"] == "scar"
    assert e2["扮演"] == "agent"            # 敌方 NPC 扮演=agent
    assert e2["行动文本"] is None           # 敌方：意图不外泄
    assert e2["反应文本"] == "侧身格挡"      # 我方反应可见

    sys_e = engine.log_system_entry("【场景】酒馆")
    assert sys_e["行动者"] is None


def test_log_pending_entry_fog(sess):
    """延迟遮盖的「进行中」预告帧：叙事未出(None)，且沿用同样的阵营可见性——敌方意图绝不提前泄露。"""
    pi = Intent(actor="player", 行动="掀翻桌子撞他", 目标="scar")
    pe = engine.log_pending_entry(sess, "player", pi)
    assert pe["叙事"] is None and pe["行动文本"] == "掀翻桌子撞他"   # 我方意图可提前显示

    ei = Intent(actor="scar", 行动="偷偷拔刀", 目标="player")
    ee = engine.log_pending_entry(sess, "scar", ei)
    assert ee["行动者"] == "scar" and ee["行动文本"] is None        # 敌方意图不提前泄露

    r_ally = Reaction(actor="aqing", 反应="接住你抛来的刀")
    assert engine.log_pending_entry(sess, "player", pi, r_ally)["反应文本"] == "接住你抛来的刀"
    r_foe = Reaction(actor="scar", 反应="挥刀格开")
    assert engine.log_pending_entry(sess, "player", pi, r_foe)["反应文本"] is None  # 敌方回应不泄露
