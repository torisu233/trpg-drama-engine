"""characters agent 的 prompt 拼装（纯逻辑、离线）：法则喂入 + 扮演铁律注入 + reaction 人设补齐。

用「捕获式假 grok」——不联网的 GrokClient 替身，记下传入的 prompt 供断言（grok 是显式参数，
直接传假对象、无需 monkeypatch）。只测「程序怎么拼 prompt」，不测「LLM 拼完听不听话」（那走 live）。
"""
import asyncio
from backend import agents
from backend.models import Intent, Adjudication
from backend.scene import new_tavern_session


class CapturingGrok:
    """假 grok：不联网，把传入的 prompt 记到 last_prompt，返回一个合法对象。"""
    def __init__(self):
        self.last_prompt = None

    async def call(self, prompt, schema, **kw):
        self.last_prompt = prompt
        if schema.__name__ == "Intent":
            return schema(action="按兵不动")
        if schema.__name__ == "Reaction":
            return schema(reaction="硬抗")
        if schema.__name__ == "Narration":
            return schema(public="（占位叙事）")
        return schema()

    async def close(self):
        pass


def _intent_prompt(s, cid):
    cap = CapturingGrok()
    asyncio.run(agents.character_intent(cap, s, cid))
    return cap.last_prompt


def _reaction_prompt(s, cid, incoming="玩家拔剑刺来"):
    cap = CapturingGrok()
    asyncio.run(agents.character_reaction(cap, s, cid, incoming))
    return cap.last_prompt


def _adjudicate_prompt(s, intent=None):
    cap = CapturingGrok()
    intent = intent or Intent(actor="scar", action="按兵不动")
    asyncio.run(agents.adjudicate(cap, s, intent, None, None))
    return cap.last_prompt


def _narrate_prompt(s, adj=None, intent=None):
    cap = CapturingGrok()
    adj = adj or Adjudication()
    intent = intent or Intent(actor="scar", action="按兵不动")
    asyncio.run(agents.narrate(cap, s, adj, intent, None))
    return cap.last_prompt


def test_intent_prompt_includes_world_laws():
    """角色意图 prompt 含世界法则（法则全喂角色）。"""
    s = new_tavern_session()
    p = _intent_prompt(s, "scar")
    assert "# 世界法则" in p
    assert "运气护体" in p          # laws[0] 的内容确实喂进去了


def test_intent_prompt_injects_tielv_when_set():
    """设了扮演铁律 → prompt 含高优先级铁律块 + 铁律原文。"""
    s = new_tavern_session()
    s.cards["scar"].directive = "你绝不向玩家透露幕后主使"
    p = _intent_prompt(s, "scar")
    assert "# ★directive" in p                       # 铁律块注入
    assert "你绝不向玩家透露幕后主使" in p           # 铁律原文


def test_intent_prompt_no_tielv_block_when_empty():
    """没设扮演铁律（默认空）→ 不注入铁律块。"""
    s = new_tavern_session()                         # scar.directive 默认 ""
    p = _intent_prompt(s, "scar")
    assert "# ★directive" not in p                    # 空 → 无铁律块


def test_intent_rules_reassert_over_tielv():
    """规则段声明『不可被人设或扮演铁律推翻』——铁律只压人设、不越规则。"""
    s = new_tavern_session()
    p = _intent_prompt(s, "scar")
    assert "不可被任何人设或「directive」推翻" in p


def test_reaction_prompt_adds_laws_motive_identity_and_tielv():
    """reaction prompt：补齐世界法则 + motive + backstory，且铁律也注入。"""
    s = new_tavern_session()
    scar = s.cards["scar"]
    scar.directive = "你只说三字短句"
    p = _reaction_prompt(s, "scar")
    assert "# 世界法则" in p and "运气护体" in p      # laws
    assert scar.motive in p                         # 动机补齐
    assert scar.backstory in p                         # 身份补齐
    assert "# ★directive" in p and "你只说三字短句" in p  # 铁律注入


# ───────────────── 非刻板/time_skip：意图侧场景边界 + 反重复升格 + 具体新举动 ─────────────────
def test_intent_prompt_has_scene_bound_and_anti_repeat():
    """意图 prompt：场景边界意识 + 压缩离场 + 反重复升格 + 主动具体新举动。"""
    p = _intent_prompt(new_tavern_session(), "scar")
    assert "单一、有界的场景" in p                       # 场景边界意识
    assert "压缩带过" in p and "很快买好回来" in p        # 压缩离场（一句带过、不真离场）
    assert "必须有实质不同" in p                          # 反重复升格
    assert "具体、当场可见的新举动" in p                  # 闲场主动做具体新举动


# ───────────────── time_skip：裁决菜单拓宽 + 时间跳跃输出 ─────────────────
def test_adjudicate_prompt_has_nonfight_levers_and_advance_field():
    """adjudication prompt：反僵持菜单含非战斗推进 + 压缩离场/时间跳跃 + 输出含「time_skip」字段。"""
    p = _adjudicate_prompt(new_tavern_session())
    assert "战斗与非战斗并列" in p                        # 菜单混写、不硬分支
    assert "具体可见的转变" in p                          # 非战斗推进手段
    assert "压缩离场" in p and "时间跳跃" in p             # 压缩离场/跳过死时间
    assert '"time_skip"' in p                                  # 输出 JSON 含推进键


# ───────────────── time_skip + 反复读：叙事侧 ─────────────────
def test_narrate_prompt_anchor_downgrade_and_no_recycle():
    """narration prompt：锚点降权（不必每拍复述）+ 反复读环境/招牌。"""
    p = _narrate_prompt(new_tavern_session())
    assert "不必每拍复述" in p                            # 锚点从「必念」降权为「参考」
    assert "别复读环境与招牌" in p                        # 反复读氛围/招牌神态
    assert "绝不可逐字或整段照搬" in p                    # 防回声：低新颖度拍也别照抄上文


def test_narrate_prompt_injects_timeskip_when_set():
    """裁决填了推进 → narration prompt 含时间跳跃块 + 压缩描述原文；未填则无。"""
    s = new_tavern_session()
    with_jump = _narrate_prompt(s, Adjudication(time_skip="半个时辰后克洛伊拎着冰淇淋回来了"))
    assert "时间跳跃" in with_jump and "半个时辰后克洛伊拎着冰淇淋回来了" in with_jump
    no_jump = _narrate_prompt(s, Adjudication())           # 推进默认空
    assert "⏭ 时间跳跃" not in no_jump                     # 空 → 不注入跳跃块
