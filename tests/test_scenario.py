"""剧本存取/转换 + 编剧合并（空栏不误清）。"""
import json
from backend.models import Scenario, AuthorReply, World, CharCard, Ledger, CharLedger
from backend import scenario as scen, config
from backend.scene import new_tavern_session


def test_scenario_roundtrip():
    """Session → Scenario → JSON → Scenario → Session 来回无损；运行期字段正确初始化。"""
    s0 = new_tavern_session()
    sc = scen.scenario_from_session(s0, "tavern")
    sc2 = Scenario(**json.loads(sc.model_dump_json()))
    s1 = scen.session_from_scenario(sc2)
    assert "怕火" in "".join(s1.角色卡["scar"].弱点)
    assert s1.角色卡["aqing"].性别 == "男"
    assert any("等同伙" in c.内容 for c in s1.会变层.场景.场景事实)
    assert s1.会变层.角色["player"].行动速度 == config.SPEED_PLAYER
    assert s1.世界观.法则
    assert s1.回合数 == 0 and s1.pending is None
    assert set(s1.记忆.keys()) == set(s1.scene.在场)
    assert any("开场" in line for line in s1.公开日志)


def test_author_merge_keeps_existing():
    """编剧合并：空栏=不更动，只改用户指定的，其他既有内容保留。"""
    sc = Scenario(
        id="t",
        世界观=World(基调="武侠", 背景="边城", 法则=["法则A"]),
        角色卡={"scar": CharCard(名="刀疤", 阵营="敌", 能力=["快刀"], 弱点=["怕火"])},
    )
    # 改 world：只加法则；基调/背景留空 → 不该被清
    scen.apply_author_reply(sc, AuthorReply(reply="", 区块="world",
        world=World(基调="", 背景="", 法则=["法则A", "法则B"])))
    assert sc.世界观.基调 == "武侠" and sc.世界观.背景 == "边城"
    assert sc.世界观.法则 == ["法则A", "法则B"]

    # 改 char：只改弱点；能力留空 → 能力不该被清
    scen.apply_author_reply(sc, AuthorReply(reply="", 区块="char", char_id="scar",
        char=CharCard(名="刀疤", 阵营="敌", 弱点=["怕火", "怕水"])))
    assert sc.角色卡["scar"].能力 == ["快刀"]
    assert sc.角色卡["scar"].弱点 == ["怕火", "怕水"]

    # ledger：添加 player 局面，不该清掉既有 scar 局面（key 级合并）
    sc.会变层.角色["scar"] = CharLedger(姿势位置="门口")
    scen.apply_author_reply(sc, AuthorReply(reply="", 区块="ledger",
        ledger=Ledger(角色={"player": CharLedger(姿势位置="桌边")})))
    assert "scar" in sc.会变层.角色 and "player" in sc.会变层.角色
