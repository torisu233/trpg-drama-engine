"""角色 agent 的 prompt 拼装（纯逻辑、离线）：法则喂入 + 扮演铁律注入 + reaction 人设补齐。

用「捕获式假 grok」——不联网的 GrokClient 替身，记下传入的 prompt 供断言（grok 是显式参数，
直接传假对象、无需 monkeypatch）。只测「程序怎么拼 prompt」，不测「LLM 拼完听不听话」（那走 live）。
"""
import asyncio
from backend import agents
from backend.scene import new_tavern_session


class CapturingGrok:
    """假 grok：不联网，把传入的 prompt 记到 last_prompt，返回一个合法对象。"""
    def __init__(self):
        self.last_prompt = None

    async def call(self, prompt, schema, **kw):
        self.last_prompt = prompt
        if schema.__name__ == "Intent":
            return schema(行动="按兵不动")
        if schema.__name__ == "Reaction":
            return schema(反应="硬抗")
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


def test_intent_prompt_includes_world_laws():
    """角色意图 prompt 含世界法则（法则全喂角色）。"""
    s = new_tavern_session()
    p = _intent_prompt(s, "scar")
    assert "# 世界法则" in p
    assert "运气护体" in p          # 法则[0] 的内容确实喂进去了


def test_intent_prompt_injects_tielv_when_set():
    """设了扮演铁律 → prompt 含高优先级铁律块 + 铁律原文。"""
    s = new_tavern_session()
    s.角色卡["scar"].扮演铁律 = "你绝不向玩家透露幕后主使"
    p = _intent_prompt(s, "scar")
    assert "# ★扮演铁律" in p                       # 铁律块注入
    assert "你绝不向玩家透露幕后主使" in p           # 铁律原文


def test_intent_prompt_no_tielv_block_when_empty():
    """没设扮演铁律（默认空）→ 不注入铁律块。"""
    s = new_tavern_session()                         # scar.扮演铁律 默认 ""
    p = _intent_prompt(s, "scar")
    assert "# ★扮演铁律" not in p                    # 空 → 无铁律块


def test_intent_rules_reassert_over_tielv():
    """规则段声明『不可被人设或扮演铁律推翻』——铁律只压人设、不越规则。"""
    s = new_tavern_session()
    p = _intent_prompt(s, "scar")
    assert "不可被任何人设或「扮演铁律」推翻" in p


def test_reaction_prompt_adds_laws_motive_identity_and_tielv():
    """反应 prompt：补齐世界法则 + 动机目标 + 身份背景，且铁律也注入。"""
    s = new_tavern_session()
    scar = s.角色卡["scar"]
    scar.扮演铁律 = "你只说三字短句"
    p = _reaction_prompt(s, "scar")
    assert "# 世界法则" in p and "运气护体" in p      # 法则
    assert scar.动机目标 in p                         # 动机补齐
    assert scar.身份背景 in p                         # 身份补齐
    assert "# ★扮演铁律" in p and "你只说三字短句" in p  # 铁律注入
