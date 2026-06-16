"""剧本存取/转换 + 编剧合并（空栏不误清）+ 不完整剧本的退化与开局闸门。"""
import json
from backend.models import Scenario, Scene, AuthorReply, World, CharCard, Ledger, CharLedger
from backend import scenario as scen, engine, config
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


# ───────────────── 不完整剧本：退化（剔孤儿）+ 开局闸门 ─────────────────
def test_session_from_scenario_prunes_orphans():
    """在场/会变层引用了不存在的角色卡（孤儿）→ 开局时剔除，ground_truth 不再 KeyError。"""
    sc = Scenario(
        id="孤儿", scene=Scene(id="s", 地点="渡口", 在场=["p1", "ghost_scene"]),
        角色卡={"p1": CharCard(名="侠", 阵营="我方", 扮演="玩家")},
        会变层=Ledger(角色={"p1": CharLedger(), "ghost_ledger": CharLedger()}),
    )
    s = scen.session_from_scenario(sc)
    assert s.scene.在场 == ["p1"]                       # 孤儿在场 id 被剔
    assert set(s.会变层.角色) == {"p1"}                  # 孤儿会变层条目被剔
    assert "侠" in engine.ground_truth(s)                # 不崩（旧代码此处 KeyError）


def test_prune_orphans_idempotent_and_on_load():
    """prune_orphans 可直接作用于既有 Session（读档侧用）；干净 Session 不受影响。"""
    s = new_tavern_session()
    before = (list(s.scene.在场), set(s.会变层.角色))
    engine.prune_orphans(s)
    assert (list(s.scene.在场), set(s.会变层.角色)) == before     # 一致剧本：无变化
    s.会变层.角色["zombie"] = CharLedger()                        # 注入孤儿
    s.scene.在场.append("zombie")
    engine.prune_orphans(s)
    assert "zombie" not in s.会变层.角色 and "zombie" not in s.scene.在场


def test_validate_playable():
    """开局闸门：完整剧本 None；缺玩家/玩家不在场/无在场角色各给出原因。"""
    assert engine.validate_playable(new_tavern_session()) is None    # 完整 → 可玩

    def _sess(sc):
        return scen.session_from_scenario(sc)

    # 无玩家（全 agent）
    no_player = _sess(Scenario(id="a", scene=Scene(id="s", 在场=["e1"]),
        角色卡={"e1": CharCard(名="匪", 阵营="敌", 扮演="agent")}))
    assert "玩家" in engine.validate_playable(no_player)

    # 玩家存在但不在「在场」→ 无行动条、永远轮不到
    off_scene = _sess(Scenario(id="b", scene=Scene(id="s", 在场=["e1"]),
        角色卡={"p1": CharCard(名="侠", 阵营="我方", 扮演="玩家"),
                "e1": CharCard(名="匪", 阵营="敌", 扮演="agent")}))
    assert "不在场" in engine.validate_playable(off_scene)

    # 无在场角色
    empty = _sess(Scenario(id="c", scene=Scene(id="s", 在场=[]), 角色卡={}))
    assert engine.validate_playable(empty) is not None
