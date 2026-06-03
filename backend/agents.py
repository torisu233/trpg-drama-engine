"""四個 agent 的封裝（裁決 / 敘事 / 角色意圖 / 角色反應）。

職責對照設計文件第十一節：
- 角色 agent：只看可見視圖 + 自己的角色卡，出意圖/反應，絕不宣告成敗
- 裁決 agent：行為裁決 + 知識裁決（雙輸出），遵守世界觀法則與角色特質，以地面真相為唯一依據
- GM/敘事 agent：依感知分發逐對象寫散文，貼世界觀基調，不發明新實體
"""
from typing import Optional
from .grok_client import GrokClient
from .models import Session, Intent, Reaction, Adjudication, Narration
from . import engine, config


def _world_brief(s: Session) -> str:
    w = s.世界觀
    parts = []
    if w.基調:
        parts.append(f"基調：{w.基調}")
    if w.背景:
        parts.append(f"背景：{w.背景}")
    return "\n".join(parts) or "（無特殊世界觀）"


def _world_laws(s: Session) -> str:
    return "\n".join(f"- {law}" for law in s.世界觀.法則) or "（無特殊法則）"


# ───────────────── 角色 agent：行動意圖 ─────────────────
async def character_intent(grok: GrokClient, s: Session, cid: str) -> Intent:
    card = s.角色卡[cid]
    view = engine.build_view(s, cid)
    mem = "\n".join(s.記憶.get(cid, [])[-6:]) or "（剛開場）"
    陣營目標 = "盡力威脅、壓制對面那桌的人" if card.陣營 == "敵" else "與玩家同陣營，協作對抗刀疤"
    prompt = f"""你在一個跑團式互動遊戲裡扮演「{card.名}」。

# 世界觀
{_world_brief(s)}

# 你是誰
陣營：{card.陣營}
身分：{card.身分背景}
性格：{"、".join(card.性格)}
說話風格：{card.說話風格}
你這場想要的：{card.動機目標}
慣用手段：{"、".join(card.行為偏好)}
你的本事：{"、".join(card.能力)}
你心裡清楚的弱點/顧忌：{"、".join(card.弱點) or "（無）"}
你的立場：{陣營目標}

# 你目前感知到的局面
{view}

# 最近發生的事（你的記憶）
{mem}

# 你的任務
輪到你行動。決定你這一拍「想做什麼」。
規則（重要）：
- 只表達意圖，**絕不宣告成敗**（不可以說「我砍中了」「我說服了他」）。
- **貼著你的說話風格、動機與慣用手段做選擇**——讓「你」有辨識度，不要像旁白。
- 顧及世界觀（例如對方若武功高強、護體難傷，硬拚未必明智）。
- 若你身負重傷或處於不利，可保守行動甚至放棄（行動填「按兵不動」）。
- 想隱蔽地行動（使眼色、暗號）就把「隱蔽」設為 true。

只輸出 JSON：
{{"行動":"攻擊/說服/後撤/移動/對話/按兵不動/...","目標":"player或aqing或scar或null","方式":"具體怎麼做，貼著你的口吻","隱蔽":false}}"""
    out = await grok.call(prompt, Intent, temperature=config.TEMP_CHARACTER, max_tokens=400)
    out.actor = cid
    return out


# ───────────────── 角色 agent：反應意圖 ─────────────────
async def character_reaction(grok: GrokClient, s: Session, cid: str, incoming: str) -> Reaction:
    card = s.角色卡[cid]
    view = engine.build_view(s, cid)
    prompt = f"""你在跑團遊戲裡扮演「{card.名}」（{card.陣營}）。
性格：{"、".join(card.性格)}；說話風格：{card.說話風格}；本事：{"、".join(card.能力)}；慣用手段：{"、".join(card.行為偏好)}。

# 世界觀
{_world_brief(s)}

# 你感知到的局面
{view}

# 正朝你而來的行動
{incoming}

# 你的任務
這是針對你的行動，你要「如何反應」。
規則：只表達反應「意圖」，**不宣告成敗**（成敗由裁決決定）。貼著你的性格與本事選擇。

只輸出 JSON：
{{"類型":"閃避/格擋/反擊/抗拒/假意順從/硬抗/後仰躲開/...","方式":"具體一句話，貼著你的口吻"}}"""
    out = await grok.call(prompt, Reaction, temperature=config.TEMP_CHARACTER, max_tokens=300)
    out.actor = cid
    return out


# ───────────────── 裁決 agent：行為 + 知識雙輸出 ─────────────────
async def adjudicate(grok: GrokClient, s: Session, intent: Intent,
                     reaction: Optional[Reaction], luck: Optional[str]) -> Adjudication:
    gt = engine.ground_truth(s)
    actor = s.角色卡.get(intent.actor)
    actor_name = actor.名 if actor else intent.actor
    intent_txt = f"{actor_name} 想：{intent.行動}" \
                 + (f" → 目標 {intent.目標}" if intent.目標 else "") \
                 + (f"；方式：{intent.方式}" if intent.方式 else "") \
                 + ("；（試圖隱蔽）" if intent.隱蔽 else "")
    react_txt = "（無人反應 / 突襲 / 對失能者）"
    if reaction:
        rn = s.角色卡.get(reaction.actor)
        react_txt = f"{rn.名 if rn else reaction.actor} 反應：{reaction.類型}；{reaction.方式}"
    luck_txt = luck or "（非爭議，不擲運氣）"
    在場 = "、".join(f"{cid}={s.角色卡[cid].名}" for cid in s.scene.在場)

    prompt = f"""你是跑團遊戲裡**中立的裁決者**。不偏袒任何一方，只依「地面真相」與「世界觀法則」裁決。

# 世界觀法則（裁決必須嚴格遵守）
{_world_laws(s)}

# 地面真相（唯一依據，含角色的能力/防禦特性/弱點，與玩家看不到的 <gm> 秘密）
{gt}

# 在場角色 id
{在場}

# 本拍行動意圖
{intent_txt}

# 對方反應意圖
{react_txt}

# 運氣神諭（隱藏，僅你可見）
{luck_txt}

# 裁決原則
- **嚴守世界觀法則與角色特質**：對有「防禦特性（如刀槍不入/橫練護體）」者，尋常刀劍拳腳無效或大打折扣；
  須循法則所列途徑（更強內力、毒、火、點穴、出其不意攻其弱點、斷其根基）才奏效。攻中對方「弱點」則效果顯著。
- 以地面真相為唯一依據。角色不能自行宣告成敗；若意圖與狀態/法則矛盾，判為不可能或受阻。
- **很少給乾淨的成功**，多數是「成功但有代價」——那個代價就是讓場面滾動的燃料。
- 後果要「質的、會改變能力」：寫「右臂中刀只能用左手」而非數值。
- 運氣：霉運→下調一階或加倒楣並發狀況；好運→容許罕見乾淨成功或有利轉折；平→照常。
- 隱蔽行動：由你決定「表象」（全場可見）與「真意」（只我方懂），並判定隱蔽是否被識破。
- **社會/資訊後果要落帳**：對話、談判、要挾若產生持久結果（招供、承諾、停火、結盟、情報揭露），
  用 ledger_delta 記為社會事實（主體填 "場景"，類別填 "社會事實" 或 "情報"），帶 gates 與可見性。
- 感知分發：判斷「誰察覺到這件事、察覺到多少」。昏迷者收不到；重傷分心可能漏看；背後動作可能未察覺。

# 輸出（只輸出 JSON）
{{
 "相關狀態": ["你查看到的、與本意圖相關的狀態/特質/法則，逐條列"],
 "逐條判定": ["每條 → 啟用/阻止/改寫/無關，一句話"],
 "可行性": "不可能/受阻/可行/需改寫",
 "結果階梯": "成功/成功但有代價/局勢逆轉",
 "ledger_delta": {{
    "add": [{{"主體":"char_id或場景","類別":"姿勢位置/身心狀況/特殊情況/空間關係/場景事實/社會事實/情報","內容":"質性事實","gates":"如何約束後續","可見性":"public"}}],
    "remove": ["要移除的狀態的關鍵字"],
    "modify": []
 }},
 "速度更新": {{"char_id": 整數速度（重傷3/瀕死2/昏迷0，正常不填）}},
 "感知更新": {{"char_id": "如 蒙眼/昏迷/重傷分心"}},
 "感知分發": {{"char_id": "全部 / 部分:只看到表象 / 無"}},
 "GM摘要": "給敘事者的一句話地面真相（這拍實際發生了什麼、收在什麼威脅上）"
}}"""
    return await grok.call(prompt, Adjudication, temperature=config.TEMP_ADJUDICATOR, max_tokens=1200)


# ───────────────── GM / 敘事 agent ─────────────────
async def narrate(grok: GrokClient, s: Session, adj: Adjudication, intent: Intent) -> Narration:
    在場 = "、".join(f"{cid}={s.角色卡[cid].名}" for cid in s.scene.在場)
    分發 = "\n".join(f"- {cid}（{s.角色卡[cid].名}）：{lvl}"
                     for cid, lvl in adj.感知分發.items()) or "- 全體：全部"
    prompt = f"""你是跑團遊戲的 GM／敘事者。把這一拍寫成貼著視角、生動的散文。

# 世界觀基調（決定文字風格）
{s.世界觀.基調 or "（中性）"}

# 在場角色 id
{在場}

# 這一拍的地面真相（你知道全部）
{adj.GM摘要}
（結果階梯：{adj.結果階梯}；可行性：{adj.可行性}）

# 感知分發（誰察覺到多少——據此決定每人版本能寫什麼）
{分發}

# 敘事原則
- **嚴禁發明新實體（最重要）**：只能描寫「地面真相摘要」與「在場角色」中已存在的人、武器、物品、環境。
  不得無中生有——例如本場景是冷兵器酒館，就**不可出現槍、子彈**，也**不可冒出摘要裡沒有的人物**（如不存在的人質）。
  摘要沒提到的細節，寧可不寫，也不要編造。武器只能是角色實際持有的那些。
- 貼世界觀基調的語氣寫；後果是質的、會改變能力。
- **這一拍必須收在一個威脅或選擇上**，逼人想回應。
- 公開版：寫全場都能看到的客觀經過（不可洩漏 <gm> 秘密或只有單方知道的真意）。
- 私密版：只為「察覺到更多」的角色加寫他獨有的感知（如我方才懂的暗號真意）；沒有額外資訊的角色可省略。
- 控制在 2-4 句，緊湊。

只輸出 JSON：
{{"公開":"全場可見的敘事","私密":{{"char_id":"該角色獨有的額外感知（可選，沒有就不要這個 key）"}}}}"""
    return await grok.call(prompt, Narration, temperature=config.TEMP_NARRATOR, max_tokens=700)
