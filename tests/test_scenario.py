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
    assert "怕火" in "".join(s1.cards["scar"].weaknesses)
    assert s1.cards["aqing"].gender == "男"
    assert any("等同伙" in c.content for c in s1.ledger.scene.scene_facts)
    assert s1.ledger.characters["player"].speed == config.SPEED_PLAYER
    assert s1.world.laws
    assert s1.turn == 0 and s1.pending is None
    assert set(s1.memory.keys()) == set(s1.scene.present)
    assert any("开场" in line for line in s1.public_log)


def test_author_merge_keeps_existing():
    """编剧合并：空栏=不更动，只改用户指定的，其他既有内容保留。"""
    sc = Scenario(
        id="t",
        world=World(tone="武侠", background="边城", laws=["法则A"]),
        cards={"scar": CharCard(name="刀疤", faction="enemy", abilities=["快刀"], weaknesses=["怕火"])},
    )
    # 改 world：只加法则；tone/背景留空 → 不该被清
    scen.apply_author_reply(sc, AuthorReply(reply="", block="world",
        world=World(tone="", background="", laws=["法则A", "法则B"])))
    assert sc.world.tone == "武侠" and sc.world.background == "边城"
    assert sc.world.laws == ["法则A", "法则B"]

    # 改 char：只改弱点；能力留空 → 能力不该被清
    scen.apply_author_reply(sc, AuthorReply(reply="", block="char", char_id="scar",
        char=CharCard(name="刀疤", faction="enemy", weaknesses=["怕火", "怕水"])))
    assert sc.cards["scar"].abilities == ["快刀"]
    assert sc.cards["scar"].weaknesses == ["怕火", "怕水"]

    # ledger：添加 player situation，不该清掉既有 scar situation（key 级合并）
    sc.ledger.characters["scar"] = CharLedger(posture="门口")
    scen.apply_author_reply(sc, AuthorReply(reply="", block="ledger",
        ledger=Ledger(characters={"player": CharLedger(posture="桌边")})))
    assert "scar" in sc.ledger.characters and "player" in sc.ledger.characters


def test_author_merge_preserves_tielv():
    """编剧编辑既有角色时，用户手填的『directive』不被清（不在 _CARD_FIELDS、走保留）。"""
    sc = Scenario(id="t", cards={"scar": CharCard(name="刀疤", faction="enemy", directive="绝不投降")})
    scen.apply_author_reply(sc, AuthorReply(reply="", block="char", char_id="scar",
        char=CharCard(name="刀疤", faction="enemy", personality=["狡猾"])))   # AI 没填铁律（默认空）
    assert sc.cards["scar"].directive == "绝不投降"   # 铁律保留、未被清
    assert sc.cards["scar"].personality == ["狡猾"]        # 正常字段照常合并


# ───────────────── 不完整剧本：退化（剔孤儿）+ 开局闸门 ─────────────────
def test_session_from_scenario_prunes_orphans():
    """present/会变层引用了不存在的角色卡（孤儿）→ 开局时剔除，ground_truth 不再 KeyError。"""
    sc = Scenario(
        id="孤儿", scene=Scene(id="s", location="渡口", present=["p1", "ghost_scene"]),
        cards={"p1": CharCard(name="侠", faction="ally", controller="player")},
        ledger=Ledger(characters={"p1": CharLedger(), "ghost_ledger": CharLedger()}),
    )
    s = scen.session_from_scenario(sc)
    assert s.scene.present == ["p1"]                       # 孤儿在场 id 被剔
    assert set(s.ledger.characters) == {"p1"}                  # 孤儿会变层条目被剔
    assert "侠" in engine.ground_truth(s)                # 不崩（旧代码此处 KeyError）


def test_prune_orphans_idempotent_and_on_load():
    """prune_orphans 可直接作用于既有 Session（读档侧用）；干净 Session 不受影响。"""
    s = new_tavern_session()
    before = (list(s.scene.present), set(s.ledger.characters))
    engine.prune_orphans(s)
    assert (list(s.scene.present), set(s.ledger.characters)) == before     # 一致剧本：无变化
    s.ledger.characters["zombie"] = CharLedger()                        # 注入孤儿
    s.scene.present.append("zombie")
    engine.prune_orphans(s)
    assert "zombie" not in s.ledger.characters and "zombie" not in s.scene.present


def test_validate_playable():
    """开局闸门：完整剧本 None；缺玩家/玩家不在场/无在场角色各给出原因。"""
    assert engine.validate_playable(new_tavern_session()) is None    # 完整 → 可玩

    def _sess(sc):
        return scen.session_from_scenario(sc)

    # 无玩家（全 agent）
    no_player = _sess(Scenario(id="a", scene=Scene(id="s", present=["e1"]),
        cards={"e1": CharCard(name="匪", faction="enemy", controller="agent")}))
    assert "player" in engine.validate_playable(no_player)

    # 玩家存在但不在「present」→ 无行动条、永远轮不到
    off_scene = _sess(Scenario(id="b", scene=Scene(id="s", present=["e1"]),
        cards={"p1": CharCard(name="侠", faction="ally", controller="player"),
                "e1": CharCard(name="匪", faction="enemy", controller="agent")}))
    assert "不在场" in engine.validate_playable(off_scene)

    # 无在场角色
    empty = _sess(Scenario(id="c", scene=Scene(id="s", present=[]), cards={}))
    assert engine.validate_playable(empty) is not None
