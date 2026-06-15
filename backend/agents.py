"""四个 agent 的封装（裁决 / 叙事 / 角色意图 / 角色反应）。

职责对照设计文档第十一节：
- 角色 agent：只看可见视图 + 自己的角色卡，出意图/反应，绝不声明成败
- 裁决 agent：行为裁决 + 知识裁决（双输出），遵守世界观法则与角色特质，以地面真相为唯一依据
- GM/叙事 agent：依感知分发逐对象写散文，贴世界观基调，不发明新实体
"""
from typing import Optional
from .grok_client import GrokClient
from .models import (
    Session, Intent, Reaction, Adjudication, Narration, Summary,
    Condition, ConsolidateOut, Scenario, AuthorReply,
)
from . import engine, config


def _roster(s: Session) -> str:
    """在场角色名册（含性别，供裁决/叙事正确归属、避免脑补）。"""
    return "、".join(
        f"{cid}={s.角色卡[cid].名}" + (f"（{s.角色卡[cid].性别}）" if s.角色卡[cid].性别 else "")
        for cid in s.scene.在场)


def _world_brief(s: Session) -> str:
    w = s.世界观
    parts = []
    if w.基调:
        parts.append(f"基调：{w.基调}")
    if w.背景:
        parts.append(f"背景：{w.背景}")
    return "\n".join(parts) or "（无特殊世界观）"


def _world_laws(s: Session) -> str:
    return "\n".join(f"- {law}" for law in s.世界观.法则) or "（无特殊法则）"


def _action_order_brief(s: Session) -> str:
    """程序算好的行动次序（谁还有几拍轮到），易读地喂给 agent；不让 AI 自己算行动值。"""
    rows = engine.action_order(s)
    if not rows:
        return ""
    parts = [f"{名}（{阵营}）{'即将行动' if 拍 <= 0 else f'约 {拍} 拍后行动'}"
             for _cid, 名, 阵营, 拍 in rows]
    return "；".join(parts)


def _mates_brief(s: Session, cid: str) -> str:
    """同阵营在场队友的整张卡（含弱点）——同阵营彼此知底，供 NPC 协同；无队友返回空串。"""
    lines = []
    for oid in engine.faction_mates(s, cid):
        c = s.角色卡[oid]
        lines.append(
            f"- {c.名}（{c.阵营}{('/' + c.性别) if c.性别 else ''}）"
            f"｜性格 {'、'.join(c.性格) or '—'}｜动机 {c.动机目标 or '—'}｜惯用手段 {'、'.join(c.行为偏好) or '—'}"
            f"｜能力 {'、'.join(c.能力) or '—'}｜防御 {'、'.join(c.防御特性) or '—'}｜弱点 {'、'.join(c.弱点) or '—'}"
        )
    return "\n".join(lines)


# ───────────────── 角色 agent：行动意图 ─────────────────
async def character_intent(grok: GrokClient, s: Session, cid: str) -> Intent:
    card = s.角色卡[cid]
    view = engine.build_view(s, cid)
    摘要 = s.摘要.get(cid, "")
    recent = "\n".join(s.记忆.get(cid, [])) or "（刚开场）"
    mem = f"【先前剧情摘要】{摘要}\n\n【最近发生】\n{recent}" if 摘要 else recent
    player_name = s.角色卡[engine.PLAYER].名 if engine.PLAYER in s.角色卡 else "玩家"
    阵营关系 = {"我方": "与玩家同阵营（倾向协作）", "敌": "与玩家敌对"}.get(card.阵营, "中立")
    中立提示 = "（你是中立第三方：不自动站队，按自己的动机目标权衡，可与任一方合作或翻脸）" if card.阵营 == "中立" else ""
    mates = _mates_brief(s, cid)
    队友段 = f"\n# 你的同阵营队友（你们彼此知底，可据此协同）\n{mates}\n" if mates else ""
    序 = _action_order_brief(s)
    prompt = f"""你在一个跑团式交互游戏里扮演「{card.名}」。

# 世界观
{_world_brief(s)}

# 你是谁
阵营：{card.阵营}　性别：{card.性别 or "未定"}
身份：{card.身份背景}
性格：{"、".join(card.性格)}
说话风格：{card.说话风格}
你这场想要的：{card.动机目标}
惯用手段：{"、".join(card.行为偏好)}
你的本事：{"、".join(card.能力)}
你心里清楚的弱点/顾忌：{"、".join(card.弱点) or "（无）"}
你与玩家的关系：{阵营关系}{中立提示}（**依你的动机目标行事，手段随情境**）
{队友段}
# 你目前感知到的局面
{view}

# 行动次序（程序算好，谁还有几拍轮到——把握节奏、谁将至/谁在逼近）
{序}

# 最近发生的事（你的记忆）
（注：叙事为第三人称具名记述、不站任何一方；主角玩家是「{player_name}」，你扮演的是「{card.名}」。）
{mem}

# 你的任务
轮到你行动。决定你这一拍「想做什么」。
规则（重要）：
- 只表达意图，**绝不声明成败**（不可以说「我砍中了」「我说服了他」）。
- **贴着你的说话风格、动机与惯用手段做选择**——让「你」有辨识度，不要像旁白。
- 顾及世界观（例如对方若武功高强、护体难伤，硬拚未必明智）。
- **推动剧情、别原地打转（重要）**：不要重复你前几拍做过的动作或说过的同一句话（同一句威胁/喊话尤其别再喊）；
  局势没进展就**换策略**——升级力度、改变目标、或转换手段（强攻／智取／撤退／求援／谈条件／服软都行），让事情往前走一步。
- **手段随情境**：这不一定是战斗场面——该谈判/交涉就谈、该欺瞒/伪装就装、该亲近/示好就亲近、该动手才动手；照你的动机与当下局面选最合适的，别无脑开打。
- 若你身负重伤或处于不利，可保守行动甚至放弃（行动填「按兵不动」）。
- 想隐蔽地行动（使眼色、暗号）就把「隐蔽」设为 true。
- 行动可以**有层次与质感**：把「你具体怎么做、怎么说、带什么神态情绪」写清楚（对话/交涉场景就给出**实际要说的话**）；可附带一个小动作（如说话同时使眼色）。但仍是**一个连贯的主要意图**，别硬塞多个重大动作；「目标」填主要对象。
- **可主动倒戈/投靠（少用、要有理由）**：若剧情让你决定改换阵营（被说服、利益所驱、恩义、识时务投降…），把「阵营切换」填目标阵营（我方/敌/中立），并在「行动」里演出这个转变。这只是**提议**，是否生效由裁决裁定（投靠我方尤其要有足够理由才被接纳）；不切换就填 null。

只输出 JSON：
{{"行动":"你想做什么——含具体做法、神态与（若有）实际对白，贴着你的口吻；可附带一个小动作","目标":"主要对象的角色id（在场者之一）或 null","隐蔽":false,"阵营切换":null}}"""
    out = await grok.call(prompt, Intent, temperature=config.TEMP_CHARACTER, max_tokens=600)
    out.actor = cid
    return out


# ───────────────── 角色 agent：反应意图 ─────────────────
async def character_reaction(grok: GrokClient, s: Session, cid: str, incoming: str) -> Reaction:
    card = s.角色卡[cid]
    view = engine.build_view(s, cid)
    性别txt = f"，{card.性别}" if card.性别 else ""
    mates = _mates_brief(s, cid)
    队友段 = f"\n# 你的同阵营队友（彼此知底）\n{mates}\n" if mates else ""
    prompt = f"""你在跑团游戏里扮演「{card.名}」（{card.阵营}{性别txt}）。
性格：{"、".join(card.性格)}；说话风格：{card.说话风格}；本事：{"、".join(card.能力)}；惯用手段：{"、".join(card.行为偏好)}。

# 世界观
{_world_brief(s)}
{队友段}
# 你感知到的局面
{view}

# 正朝你而来的行动
{incoming}

# 你的任务
你被点名了，决定「你要如何回应」——可防御（闪避/格挡）、反击、还嘴、喝止、配合/顺从、虚与委蛇、顺势而为…依情境与你的性格选择（不一定是打斗）。
规则：只表达回应「意图」，**不声明成败**（成败由裁决决定）。

只输出 JSON：
{{"反应":"一句话：你要如何回应（含具体做法），贴着你的口吻"}}"""
    out = await grok.call(prompt, Reaction, temperature=config.TEMP_CHARACTER, max_tokens=300)
    out.actor = cid
    return out


# ───────────────── 裁决 agent：行为 + 知识双输出 ─────────────────
async def adjudicate(grok: GrokClient, s: Session, intent: Intent,
                     reaction: Optional[Reaction], luck: Optional[str]) -> Adjudication:
    gt = engine.ground_truth(s)
    actor = s.角色卡.get(intent.actor)
    actor_name = actor.名 if actor else intent.actor
    intent_txt = f"{actor_name} 想：{intent.行动}" \
                 + (f" → 目标 {intent.目标}" if intent.目标 else "") \
                 + ("；（试图隐蔽，想瞒过敌人）" if intent.隐蔽 else "")
    react_txt = "（无人反应 / 突袭 / 对失能者）"
    if reaction:
        rn = s.角色卡.get(reaction.actor)
        react_txt = f"{rn.名 if rn else reaction.actor} 回应：{reaction.反应}"
    luck_txt = luck or "（非争议，不掷运气）"
    在场 = _roster(s)
    近期 = "\n".join(s.公开日志[-4:]) or "（开场）"
    序 = _action_order_brief(s)

    prompt = f"""你是跑团游戏里**中立的裁决者**。不偏袒任何一方，只依「地面真相」与「世界观法则」裁决。

# 世界观法则（裁决必须严格遵守）
{_world_laws(s)}

# 地面真相（唯一依据，含角色的能力/防御特性/弱点，与玩家看不到的 <gm> 秘密）
{gt}

# 在场角色 id
{在场}

# 本拍行动意图
{intent_txt}

# 对方反应意图
{react_txt}

# 运气神谕（隐藏，仅你可见）
{luck_txt}

# 最近几拍（判断是否在原地重复、该不该推进；现在是第 {s.回合数} 拍）
{近期}

# 行动次序（程序算好，谁还有几拍轮到——判断推进、以及「援兵/追兵/火势」等逼近之事何时兑现的参考）
{序}

# 裁决原则
- **严守世界观法则与角色特质**：对有「防御特性（如刀枪不入/横练护体）」者，寻常刀剑拳脚无效或大打折扣；
  须循法则所列途径（更强内力、毒、火、点穴、出其不意攻其弱点、断其根基）才奏效。攻中对方「弱点」则效果显著。
- 以地面真相为唯一依据。角色不能自行声明成败；若意图与状态/法则矛盾，判为不可能或受阻。
- **很少给干净的成功**，多数是「成功但有代价」——那个代价就是让场面滚动的燃料。
- **不容僵持、推动剧情（重要）**：若最近几拍在原地重复（同样的动作/对话循环、谁也没真正前进），本拍就让局势**质变**，
  别再给「拉锯不动」的结果——让开场埋下的悬置威胁随时间**兑现**（如地面真相写「援兵数招内到」就让敌方援兵到场）、
  让环境危机升级逼人抉择（火势失控、退路将断、时限将尽）、或让反复无效的一方付出实质代价、可选项被削减。
- **时间在流动**：地面真相里「即将到来／正在逼近」的事（援兵、追兵、火势、时限）不可无限拖延，应随回合推进而兑现，把场景推向解决或新阶段。
- 后果要「质的、会改变能力」：写「右臂中刀只能用左手」而非数值。
- **交互不限战斗，同一套裁决适用所有模式**——用该模式合适的质性后果，别硬套伤势：
  · 对话/交涉 → 信任/起疑/动摇/让步/把柄/承诺（多记为社会事实）
  · 伪装/潜入 → 是否被识破或起疑、掩护是否成立、露出的身份线索（用隐蔽与感知分发）
- 运气：霉运→下调一阶或加倒楣并发状况；好运→容许罕见干净成功或有利转折；平→照常。
- 隐蔽行动：由你决定「表象」（全场可见）与「真意」（只我方懂），并判定隐蔽是否被识破。
- **复合行动**：一拍可能含「一个主要动作 + 附带小动作」（如攻击同时打暗号、后撤同时嘲讽）。请**逐部分裁决**，
  并权衡「一心二用」的代价——通常主要动作打折、或附带动作不完全到位（正是「成功但有代价」的好题材）。
  「目标」只是主要反应对象；附带对象（如收暗号的队友）由你在感知分发处理，不必另收反应。
- **社会/信息后果要落账**：对话、谈判、要挟若产生持久结果（招供、承诺、停火、结盟、情报揭露），
  用 ledger_delta 记为社会事实（主体填 "场景"，类别填 "社会事实" 或 "情报"），带 gates 与可见性。
- **瞬态状态设期限**：姿势晃动/被惊吓/火光蔓延/暂时失衡等短暂状态，add 时设「剩余拍数」(1-3，几拍后自动消失)；
  伤势/中毒/承诺/情绪转变/社会事实等持久状态留 null（不填）。
- **升级即删旧、严禁堆栈近义状态**：当某状态恶化/被取代（火越烧越旺、伤势加重、姿势改变），
  **先把旧版本关键字放进 remove，再 add 新版本**——绝不让账本同时存在多条描述同一件事的近义状态。
- **同一事实只记一处**：招供/承诺/情报记成「社会事实」即可，**不要又拷贝一份到角色身心状况**。
- 可见性只能填这四种之一：`public` / `gm` / `faction:阵营` / `self:角色id`（不要自创其他值）。
- 感知分发：判断「谁察觉到这件事、察觉到多少」。昏迷者收不到；重伤分心可能漏看；背后动作可能未察觉。
- **阵营变更（倒戈/投靠/被策反/投降）**：若某角色提议切换阵营（见行动意图的「阵营切换」）或剧情让其改换立场，**需有足够叙事依据**才批准，写进「阵营变更」(char_id→新阵营 我方/敌/中立)；**投靠「我方」门槛要高**（须被说服/有恩义/利益足够，不能凭空宣布）。批准了就在 GM摘要 点出这次转变，让叙事交代清楚。阵营只用 我方/敌/中立。

# 输出（只输出 JSON）
{{
 "相关状态": ["你查看到的、与本意图相关的状态/特质/法则，逐条列"],
 "逐条判定": ["每条 → 激活/阻止/改写/无关，一句话"],
 "可行性": "不可能/受阻/可行/需改写",
 "结果阶梯": "成功/成功但有代价/局势逆转",
 "ledger_delta": {{
    "add": [{{"主体":"char_id或场景","类别":"姿势位置/身心状况/特殊情况/空间关系/场景事实/社会事实/情报","内容":"质性事实","gates":"如何约束后续","可见性":"public","剩余拍数":null}}],
    "remove": ["要移除的状态的关键字"],
    "modify": []
 }},
 "速度更新": {{"char_id": 整数速度（重伤3/濒死2/昏迷0，正常不填）}},
 "感知更新": {{"char_id": "如 蒙眼/昏迷/重伤分心"}},
 "阵营变更": {{"char_id": "我方/敌/中立（仅在批准倒戈/投靠/被策反时填，否则留空）"}},
 "感知分发": {{"char_id": "全部 / 部分:只看到表象 / 无"}},
 "GM摘要": "给叙事者的一句话地面真相（这拍实际发生了什么、收在什么未决张力上：威胁/疑点/抉择）"
}}"""
    return await grok.call(prompt, Adjudication, temperature=config.TEMP_ADJUDICATOR, max_tokens=1200)


# ───────────────── GM / 叙事 agent ─────────────────
def _vis_label(v: str) -> str:
    if v == "public":
        return "公开"
    if v.startswith("faction"):
        return "仅该阵营知"
    if v.startswith("self"):
        return "仅本人知"
    return "机密gm，公开版绝不可写"


async def narrate(grok: GrokClient, s: Session, adj: Adjudication, intent: Intent,
                  reaction: Optional[Reaction] = None) -> Narration:
    在场 = _roster(s)
    pcard = s.角色卡.get(engine.PLAYER)
    player_name = pcard.名 if pcard else "玩家"
    序 = _action_order_brief(s)
    分发 = "\n".join(f"- {cid}（{s.角色卡[cid].名}）：{lvl}"
                     for cid, lvl in adj.感知分发.items()) or "- 全体：全部"

    actor = s.角色卡.get(intent.actor)
    actor_name = actor.名 if actor else intent.actor
    行动者行 = f"{actor_name} 声明：{intent.行动}" \
               + (f"（目标 {intent.目标}）" if intent.目标 else "") \
               + ("（试图隐蔽）" if intent.隐蔽 else "")
    反应行 = ""
    if reaction:
        rn = s.角色卡.get(reaction.actor)
        反应行 = f"\n# 对方回应\n{rn.名 if rn else reaction.actor}：{reaction.反应}"
    变更 = "\n".join(f"- {d.内容}（{_vis_label(d.可见性)}）" for d in adj.ledger_delta.add) \
           or "（本拍无添加状态）"
    近期叙事 = "\n".join(s.公开日志[-2:]) or "（开场）"
    公开锚点 = "；".join(c.内容 for c in (s.会变层.场景.空间关系 + s.会变层.场景.场景事实)
                        if c.可见性 == "public") or "（无）"
    判定材料 = ""
    if adj.相关状态 or adj.逐条判定:
        判定材料 = ("\n# 本拍涉及的事实与判定（可据此充分描写，但别超出这些事实）\n"
                   "相关状态：" + "；".join(adj.相关状态) +
                   "\n判定：" + "；".join(adj.逐条判定))
    参与 = [intent.actor] + ([reaction.actor] if reaction else [])
    口吻rows = []
    for cid in 参与:
        c = s.角色卡.get(cid)
        if c:
            口吻rows.append(f"- {c.名}：性格 {('、'.join(c.性格)) or '—'}；口吻 {c.说话风格 or '—'}")
    口吻txt = ("\n# 登场者性格与口吻（让对白与神态贴着角色）\n" + "\n".join(口吻rows)) if 口吻rows else ""

    prompt = f"""你是跑团游戏的 GM／叙事者。把这一拍写成**中立第三人称**、生动的散文。

# 世界观基调（决定文字风格）
{s.世界观.基调 or "（中性）"}

# 在场角色 id
{在场}

# 故事进展（玩家刚看到的；承接它，但**绝不可重述**已写过的事件或对白）
{近期叙事}

# 目前场面（公开锚点，保持一致、别写出矛盾）
{公开锚点}

# 行动节奏（程序算好，谁还有几拍轮到）
{序}
（用途：把握「谁快到、谁在逼近」——若有人还要好几拍才到（如赶来的援兵/追兵），可顺势铺垫其**逐渐逼近**的氛围（脚步声渐近、马蹄由远及近、尚在门外）；越近笔墨越紧。**但绝不可把「拍」这种游戏数字写进叙事**，只用自然笔法。）

# 本拍行动者
{行动者行}{反应行}
{口吻txt}

# 这一拍的地面真相（你知道全部）
{adj.GM摘要}
（结果阶梯：{adj.结果阶梯}；可行性：{adj.可行性}）

# 本拍实际造成的状态变更（忠实据此叙事，注意每条的可见性）
{变更}
{判定材料}

# 感知分发（谁察觉到多少——据此决定每人版本能写什么）
{分发}

# 叙事视角（最重要，先于一切）：中立第三人称、具名、不站任何一方
- 公开叙事是**一份对所有人都成立的客观记述**——玩家与每个角色 agent 都会读到它并据此行动。**一律第三人称、直呼角色名**（含玩家角色「{player_name}」），**绝不用「你／你们」**，也绝不用「我方／敌方／友军／我们」这类**随立场变化**的词；否则不同立场的读者（尤其 NPC agent）会把指代弄反。
- **用「身份／归属」（绝对）描述，不用「立场」（相对）**：写人物名字或其所属（「漕帮的汉子」「客栈伙计」「黑衣人」），不写「敌人／援兵／友军」。确需点出相对关系时**显式归到具名角色**——写「来接应刀疤的几名漕帮汉子」而非「援兵」，写「与阿青敌对的那人」而非「敌人」。
- 私密版：给「察觉到更多」的某 NPC 补其独有感知，用该 NPC 名下的视角写（同样具名、不用「你」）。

# 叙事原则
- **只写本拍的新发展（最重要）**：承接上方「故事进展」，但**不可复述已写过的事件或对白**；同一角色别把类似的话再讲一次。
  本拍若只是「继续拖延/僵持」，就只写这拍**添加**的细节（一个眼神、半步移动、一句新话），别重描整个场面。
- **准确归属、忠于事实（同样关键）**：严格按上面「行动者 / 对方回应 / 状态变更」写「**谁**做了什么、**谁**被影响」。
  不可张冠李戴（把某人的事写到另一人头上，如该是「阿青的绕背意图被识破」却写成「玩家无处藏身」）；
  不可改写事件性质（如把「计谋被识破」写成「某人暴露躲藏」）。摘要/变更没说的因果，不要自行发明。
- **严禁发明新实体**：只能描写地面真相与在场角色中已存在的人、武器、物品、环境（冷兵器酒馆不可出现枪、子弹，不可冒出不存在的人物）。
- 贴世界观基调的语气写；后果是质的、会改写下一步的可能（战斗写伤势，交涉写人心向背，潜入写疑点）。
- **这一拍必须收在一个未决的张力上**（威胁、疑点、抉择皆可），逼人想回应。
- 节奏随基调与模式：打斗可急，交涉可缓可柔，不必都用战斗节奏。
- 公开版：只写全场可见的客观经过；**标「机密gm」或「仅本人/仅该阵营知」的变更，绝不可写进公开版**。
- 私密版：只为「察觉到更多」的角色加写他独有的感知（如我方才懂的暗号真意）；没有额外信息的角色可省略。
- **长度随份量（时间弹性）**：平淡过场一两句带过即可；**有戏的关键拍要充分铺陈成一段**（约 3–6 句），调动上面的「相关状态与判定、角色性格口吻、场景锚点」，写出神态、动作、对白、情绪的质感——别每拍都干瘪。
- **充分但不杜撰**：可以在已提供的事实上尽情演绎（感官、心理、语气、节奏），但**所有具体细节都必须源自上面给的材料**（地面真相/相关状态与判定/状态变更/角色口吻/场景锚点），不得发明新事实或新实体。

只输出 JSON：
{{"公开":"全场可见的叙事","私密":{{"char_id":"该角色独有的额外感知（可选，没有就不要这个 key）"}}}}"""
    return await grok.call(prompt, Narration, temperature=config.TEMP_NARRATOR, max_tokens=1000)


# ───────────────── 滚动摘要：压缩旧叙事，保连贯（只管文气，不记事实） ─────────────────
async def summarize_memory(grok: GrokClient, s: Session, cid: str,
                           old: str, evicted: list) -> str:
    name = s.角色卡[cid].名
    block = "\n".join(evicted)
    prompt = f"""你在维护「{name}」的剧情记忆摘要，供其后续扮演保持连贯。
把【既有摘要】与【接下来发生的数拍】融合成**一段精简、连贯**的摘要。

# 既有摘要
{old or "（无，这是第一次压缩）"}

# 新发生的数拍（需并入摘要，之后不再逐字保留）
{block}

# 要求
- 以「{name}」的视角与已知来写，保留：剧情走向、与各方的关系/恩怨变化、情绪起伏、未解的张力与悬念。
- **不要记录精确状态数据**（谁伤在哪、谁站哪、确切承诺——那些另有账本）；你只负责「故事感」与连贯。
- 精简，约 120 字内，一段话。

只输出 JSON：{{"摘要":"..."}}"""
    out = await grok.call(prompt, Summary, temperature=0.4, max_tokens=400)
    return out.摘要


# ───────────────── 账本整理：合并近义条目、清冗余（不改变事实） ─────────────────
async def consolidate_conditions(grok: GrokClient, s: Session, label: str,
                                 conds: list) -> list:
    """把一份条目清单里描述同一件事的近义条目合并成单一条目。返回整理后的 Condition 清单。"""
    lines = "\n".join(f"- {c.内容}｜gates:{c.gates}｜{c.可见性}" for c in conds)
    prompt = f"""你在整理跑团游戏的状态账本「{label}」，移除冗余，但**不改变事实**。

下列条目可能有多条描述同一件事的近义条目（例如反复出现「先还债再谈」）。请：
- 把描述同一件事的近义条目**合并成单一精简条目**；
- 移除已被取代或互相矛盾的旧条目；
- 保留彼此**真正不同**的事实，别把不同的事压成一条；
- 保留每条的 gates 与可见性；**不要添加**原本没有的事实。

目前清单：
{lines}

只输出 JSON：{{"conditions":[{{"内容":"精简事实","gates":"如何约束后续","可见性":"public"}}]}}"""
    out = await grok.call(prompt, ConsolidateOut, temperature=0.2, max_tokens=900)
    return [Condition(内容=c.内容, gates=c.gates, 可见性=c.可见性, 来源="整理")
            for c in out.conditions]


# ───────────────── 编剧 agent：与用户协作设计剧本（区块式编辑） ─────────────────
def _scenario_brief(sc: Scenario) -> str:
    w, L = sc.世界观, sc.会变层
    lines = [
        f"世界观：基调={w.基调 or '（空）'}｜法则 {len(w.法则)} 条｜背景{'已写' if w.背景 else '（空）'}",
        f"场景：地点={sc.scene.地点 or '（空）'}｜钩子{'已写' if sc.scene.钩子 else '（空）'}｜在场={sc.scene.在场 or '（空）'}",
    ]
    if sc.角色卡:
        for cid, c in sc.角色卡.items():
            lines.append(f"角色[{cid}]：{c.名}（{c.阵营}/{c.性别 or '?'}）能力{len(c.能力)}/防御{len(c.防御特性)}/弱点{len(c.弱点)}")
    else:
        lines.append("角色：（尚无）")
    lines.append(f"初始局面：已配置角色 {len(L.角色)}｜空间关系{len(L.场景.空间关系)}｜场景事实{len(L.场景.场景事实)}｜社会事实{len(L.场景.社会事实)}")
    return "\n".join(lines)


def author_missing(sc: Scenario) -> list:
    m = []
    if not sc.世界观.基调:
        m.append("世界观基调")
    if not sc.scene.地点:
        m.append("场景地点")
    if not sc.scene.钩子:
        m.append("开场钩子")
    if not any(c.扮演 == "玩家" for c in sc.角色卡.values()):
        m.append("玩家角色")
    if not any(c.阵营 == "敌" for c in sc.角色卡.values()):
        m.append("至少一个敌人")
    if not sc.会变层.角色:
        m.append("初始局面（姿势/速度/行动值）")
    return m


async def author_turn(grok: GrokClient, sc: Scenario, history: list, user_msg: str) -> AuthorReply:
    brief = _scenario_brief(sc)
    缺 = "、".join(author_missing(sc)) or "（基本要件看来已齐）"
    hist = "\n".join(f"{r}：{t}" for r, t in history[-6:]) or "（刚开始）"
    在场ids = "、".join(sc.scene.在场) or "（尚无）"
    prompt = f"""你是跑团游戏的「编剧」，与用户协作设计一份剧本。你要主动提案、填入具体草稿，而非只问空泛问题。

# 编剧守则（决定品质）
- 角色卡双用：演戏栏（性格/说话风格/动机目标/行为偏好）＋裁决栏（能力/防御特性/弱点）；务必补上「性别」与外貌年龄（写进身份背景），避免被脑补弄错。
- **把关键弱点设成秘密**：放在角色卡「弱点」，并可在会变层用 可见性=gm 埋线索；别让玩家开局就知道（可被游戏中发现利用）。
- 世界观「法则」要能**影响裁决**（例：某类高手刀枪不入、轻功可飞檐走壁、内伤难愈）。
- **埋钩子与张力**：开场 hook 要逼玩家立刻回应；用场景事实/社会事实提供筹码与变量（债务、人质、恩怨、出口封死）。
- 会变层初始化：每个在场角色的「姿势位置、行动速度(玩家7/常5/快6/负伤4)、感知能力」；必要时设「初始行动值」做先机（埋伏者高）；空间关系与场景事实；社会事实。
- 可见性只用：public / gm / faction:阵营 / self:角色id。
- **阵营只用「我方」「敌」「中立」三选一**（玩家与队友＝我方，对手＝敌，掮客/线人/旁观者等第三方＝中立；引擎据此判敌我，不可自创其他值）。阵营可在游玩中由角色倒戈/被策反而改变，你只需设好初始阵营。
- 角色 id 用简短英文（如 player/aqing/scar）；玩家角色的「扮演」填「玩家」，其余填「agent」。
- 能力/防御特性/弱点一律用**质性描述**，**不要写数值**（写「旧伤复发时使不上力」而非「行动值-2」）。

# 目前剧本状态
{brief}
在场角色 id：{在场ids}

# 还缺/待决
{缺}

# 最近对话
{hist}

# 用户这句话
{user_msg}

# 你的任务（重要）
**优先回应用户的明确要求**：若要求关于某个角色（名字/性格/能力/弱点/秘密/外貌），就**更新该角色的 char 区块**（角色卡是剧本内核，别一直延后到「待补」）。没有特别指向时，挑「还缺/待决」中最关键的一项补上（通常是还没建的角色卡）。
理解用户意图，**本回合只更新一个区块**：
- 区块="world" → 填 world（World：基调/背景/法则）
- 区块="scene" → 填 scene（Scene：id/地点/钩子/在场）
- 区块="char" → 填 char_id 与 char（一张完整角色卡）
- 区块="ledger" → 填 ledger（完整初始会变层；**沿用已有的，再加新的**，别漏掉已配置的角色）
- 区块="none" → 纯提问或建议，不更新
把对应区块的字段**完整填好**，其余区块字段留 null。reply 简短说明你做了什么或要问什么并引导下一步。
**保留既有内容（重要）**：编辑某区块时只动用户要求改的部分，该区块**其他既有字段要照原样一并带上**（例如只改世界法则时，基调/背景要原样返回，别留空）。系统把空栏视为「不更动」，故不必怕，但能带就带；ledger 的角色字典只会「更新你给的、保留你没给的」。
missing 列出还缺的关键部分；当「世界观基调+场景+钩子+玩家+至少一敌+基本初始局面」齐备时 done=true。

只输出 JSON（依 schema；未更新的区块字段填 null）。"""
    return await grok.call(prompt, AuthorReply, temperature=0.7, max_tokens=2500)
