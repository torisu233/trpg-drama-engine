"""四個 agent 的封裝（裁決 / 敘事 / 角色意圖 / 角色反應）。

職責對照設計文件第十一節：
- 角色 agent：只看可見視圖 + 自己的角色卡，出意圖/反應，絕不宣告成敗
- 裁決 agent：行為裁決 + 知識裁決（雙輸出），遵守世界觀法則與角色特質，以地面真相為唯一依據
- GM/敘事 agent：依感知分發逐對象寫散文，貼世界觀基調，不發明新實體
"""
from typing import Optional
from .grok_client import GrokClient
from .models import (
    Session, Intent, Reaction, Adjudication, Narration, Summary,
    Condition, ConsolidateOut, Scenario, AuthorReply,
)
from . import engine, config


def _roster(s: Session) -> str:
    """在場角色名冊（含性別，供裁決/敘事正確歸屬、避免腦補）。"""
    return "、".join(
        f"{cid}={s.角色卡[cid].名}" + (f"（{s.角色卡[cid].性別}）" if s.角色卡[cid].性別 else "")
        for cid in s.scene.在場)


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
    摘要 = s.摘要.get(cid, "")
    recent = "\n".join(s.記憶.get(cid, [])) or "（剛開場）"
    mem = f"【先前劇情摘要】{摘要}\n\n【最近發生】\n{recent}" if 摘要 else recent
    陣營關係 = {"我方": "與玩家同陣營（傾向協作）", "敵": "與玩家敵對"}.get(card.陣營, "中立")
    prompt = f"""你在一個跑團式互動遊戲裡扮演「{card.名}」。

# 世界觀
{_world_brief(s)}

# 你是誰
陣營：{card.陣營}　性別：{card.性別 or "未定"}
身分：{card.身分背景}
性格：{"、".join(card.性格)}
說話風格：{card.說話風格}
你這場想要的：{card.動機目標}
慣用手段：{"、".join(card.行為偏好)}
你的本事：{"、".join(card.能力)}
你心裡清楚的弱點/顧忌：{"、".join(card.弱點) or "（無）"}
你與玩家的關係：{陣營關係}（**依你的動機目標行事，手段隨情境**）

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
- **手段隨情境**：這不一定是戰鬥場面——該談判/交涉就談、該欺瞞/偽裝就裝、該親近/示好就親近、該動手才動手；照你的動機與當下局面選最合適的，別無腦開打。
- 若你身負重傷或處於不利，可保守行動甚至放棄（行動填「按兵不動」）。
- 想隱蔽地行動（使眼色、暗號）就把「隱蔽」設為 true。
- 行動可以**有層次與質感**：把「你具體怎麼做、怎麼說、帶什麼神態情緒」寫清楚（對話/交涉場景就給出**實際要說的話**）；可附帶一個小動作（如說話同時使眼色）。但仍是**一個連貫的主要意圖**，別硬塞多個重大動作；「目標」填主要對象。

只輸出 JSON：
{{"行動":"你想做什麼——含具體做法、神態與（若有）實際對白，貼著你的口吻；可附帶一個小動作","目標":"主要對象的角色id（在場者之一）或 null","隱蔽":false}}"""
    out = await grok.call(prompt, Intent, temperature=config.TEMP_CHARACTER, max_tokens=600)
    out.actor = cid
    return out


# ───────────────── 角色 agent：反應意圖 ─────────────────
async def character_reaction(grok: GrokClient, s: Session, cid: str, incoming: str) -> Reaction:
    card = s.角色卡[cid]
    view = engine.build_view(s, cid)
    性別txt = f"，{card.性別}" if card.性別 else ""
    prompt = f"""你在跑團遊戲裡扮演「{card.名}」（{card.陣營}{性別txt}）。
性格：{"、".join(card.性格)}；說話風格：{card.說話風格}；本事：{"、".join(card.能力)}；慣用手段：{"、".join(card.行為偏好)}。

# 世界觀
{_world_brief(s)}

# 你感知到的局面
{view}

# 正朝你而來的行動
{incoming}

# 你的任務
你被點名了，決定「你要如何回應」——可防禦（閃避/格擋）、反擊、還嘴、喝止、配合/順從、虛與委蛇、順勢而為…依情境與你的性格選擇（不一定是打鬥）。
規則：只表達回應「意圖」，**不宣告成敗**（成敗由裁決決定）。

只輸出 JSON：
{{"反應":"一句話：你要如何回應（含具體做法），貼著你的口吻"}}"""
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
                 + ("；（試圖隱蔽，想瞞過敵人）" if intent.隱蔽 else "")
    react_txt = "（無人反應 / 突襲 / 對失能者）"
    if reaction:
        rn = s.角色卡.get(reaction.actor)
        react_txt = f"{rn.名 if rn else reaction.actor} 回應：{reaction.反應}"
    luck_txt = luck or "（非爭議，不擲運氣）"
    在場 = _roster(s)

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
- **互動不限戰鬥，同一套裁決適用所有模式**——用該模式合適的質性後果，別硬套傷勢：
  · 對話/交涉 → 信任/起疑/動搖/讓步/把柄/承諾（多記為社會事實）
  · 偽裝/潛入 → 是否被識破或起疑、掩護是否成立、露出的身分線索（用隱蔽與感知分發）
- 運氣：霉運→下調一階或加倒楣並發狀況；好運→容許罕見乾淨成功或有利轉折；平→照常。
- 隱蔽行動：由你決定「表象」（全場可見）與「真意」（只我方懂），並判定隱蔽是否被識破。
- **複合行動**：一拍可能含「一個主要動作 + 附帶小動作」（如攻擊同時打暗號、後撤同時嘲諷）。請**逐部分裁決**，
  並權衡「一心二用」的代價——通常主要動作打折、或附帶動作不完全到位（正是「成功但有代價」的好題材）。
  「目標」只是主要反應對象；附帶對象（如收暗號的隊友）由你在感知分發處理，不必另收反應。
- **社會/資訊後果要落帳**：對話、談判、要挾若產生持久結果（招供、承諾、停火、結盟、情報揭露），
  用 ledger_delta 記為社會事實（主體填 "場景"，類別填 "社會事實" 或 "情報"），帶 gates 與可見性。
- **瞬態狀態設期限**：姿勢晃動/被驚嚇/火光蔓延/暫時失衡等短暫狀態，add 時設「剩餘拍數」(1-3，幾拍後自動消失)；
  傷勢/中毒/承諾/情緒轉變/社會事實等持久狀態留 null（不填）。
- **升級即刪舊、嚴禁堆疊近義狀態**：當某狀態惡化/被取代（火越燒越旺、傷勢加重、姿勢改變），
  **先把舊版本關鍵字放進 remove，再 add 新版本**——絕不讓帳本同時存在多條描述同一件事的近義狀態。
- **同一事實只記一處**：招供/承諾/情報記成「社會事實」即可，**不要又複製一份到角色身心狀況**。
- 可見性只能填這四種之一：`public` / `gm` / `faction:陣營` / `self:角色id`（不要自創其他值）。
- 感知分發：判斷「誰察覺到這件事、察覺到多少」。昏迷者收不到；重傷分心可能漏看；背後動作可能未察覺。

# 輸出（只輸出 JSON）
{{
 "相關狀態": ["你查看到的、與本意圖相關的狀態/特質/法則，逐條列"],
 "逐條判定": ["每條 → 啟用/阻止/改寫/無關，一句話"],
 "可行性": "不可能/受阻/可行/需改寫",
 "結果階梯": "成功/成功但有代價/局勢逆轉",
 "ledger_delta": {{
    "add": [{{"主體":"char_id或場景","類別":"姿勢位置/身心狀況/特殊情況/空間關係/場景事實/社會事實/情報","內容":"質性事實","gates":"如何約束後續","可見性":"public","剩餘拍數":null}}],
    "remove": ["要移除的狀態的關鍵字"],
    "modify": []
 }},
 "速度更新": {{"char_id": 整數速度（重傷3/瀕死2/昏迷0，正常不填）}},
 "感知更新": {{"char_id": "如 蒙眼/昏迷/重傷分心"}},
 "感知分發": {{"char_id": "全部 / 部分:只看到表象 / 無"}},
 "GM摘要": "給敘事者的一句話地面真相（這拍實際發生了什麼、收在什麼未決張力上：威脅/疑點/抉擇）"
}}"""
    return await grok.call(prompt, Adjudication, temperature=config.TEMP_ADJUDICATOR, max_tokens=1200)


# ───────────────── GM / 敘事 agent ─────────────────
def _vis_label(v: str) -> str:
    if v == "public":
        return "公開"
    if v.startswith("faction"):
        return "僅該陣營知"
    if v.startswith("self"):
        return "僅本人知"
    return "機密gm，公開版絕不可寫"


async def narrate(grok: GrokClient, s: Session, adj: Adjudication, intent: Intent,
                  reaction: Optional[Reaction] = None) -> Narration:
    在場 = _roster(s)
    分發 = "\n".join(f"- {cid}（{s.角色卡[cid].名}）：{lvl}"
                     for cid, lvl in adj.感知分發.items()) or "- 全體：全部"

    actor = s.角色卡.get(intent.actor)
    actor_name = actor.名 if actor else intent.actor
    行動者行 = f"{actor_name} 宣告：{intent.行動}" \
               + (f"（目標 {intent.目標}）" if intent.目標 else "") \
               + ("（試圖隱蔽）" if intent.隱蔽 else "")
    反應行 = ""
    if reaction:
        rn = s.角色卡.get(reaction.actor)
        反應行 = f"\n# 對方回應\n{rn.名 if rn else reaction.actor}：{reaction.反應}"
    變更 = "\n".join(f"- {d.內容}（{_vis_label(d.可見性)}）" for d in adj.ledger_delta.add) \
           or "（本拍無新增狀態）"
    近期敘事 = "\n".join(s.公開日誌[-2:]) or "（開場）"
    公開錨點 = "；".join(c.內容 for c in (s.會變層.場景.空間關係 + s.會變層.場景.場景事實)
                        if c.可見性 == "public") or "（無）"
    判定材料 = ""
    if adj.相關狀態 or adj.逐條判定:
        判定材料 = ("\n# 本拍涉及的事實與判定（可據此充分描寫，但別超出這些事實）\n"
                   "相關狀態：" + "；".join(adj.相關狀態) +
                   "\n判定：" + "；".join(adj.逐條判定))
    參與 = [intent.actor] + ([reaction.actor] if reaction else [])
    口吻rows = []
    for cid in 參與:
        c = s.角色卡.get(cid)
        if c:
            口吻rows.append(f"- {c.名}：性格 {('、'.join(c.性格)) or '—'}；口吻 {c.說話風格 or '—'}")
    口吻txt = ("\n# 登場者性格與口吻（讓對白與神態貼著角色）\n" + "\n".join(口吻rows)) if 口吻rows else ""

    prompt = f"""你是跑團遊戲的 GM／敘事者。把這一拍寫成貼著視角、生動的散文。

# 世界觀基調（決定文字風格）
{s.世界觀.基調 or "（中性）"}

# 在場角色 id
{在場}

# 故事進展（玩家剛看到的；承接它，但**絕不可重述**已寫過的事件或對白）
{近期敘事}

# 目前場面（公開錨點，保持一致、別寫出矛盾）
{公開錨點}

# 本拍行動者
{行動者行}{反應行}
{口吻txt}

# 這一拍的地面真相（你知道全部）
{adj.GM摘要}
（結果階梯：{adj.結果階梯}；可行性：{adj.可行性}）

# 本拍實際造成的狀態變更（忠實據此敘事，注意每條的可見性）
{變更}
{判定材料}

# 感知分發（誰察覺到多少——據此決定每人版本能寫什麼）
{分發}

# 敘事原則
- **只寫本拍的新發展（最重要）**：承接上方「故事進展」，但**不可復述已寫過的事件或對白**；同一角色別把類似的話再講一次。
  本拍若只是「繼續拖延/僵持」，就只寫這拍**新增**的細節（一個眼神、半步移動、一句新話），別重描整個場面。
- **準確歸屬、忠於事實（同樣關鍵）**：嚴格按上面「行動者 / 對方回應 / 狀態變更」寫「**誰**做了什麼、**誰**被影響」。
  不可張冠李戴（把某人的事寫到另一人頭上，如該是「阿青的繞背意圖被識破」卻寫成「玩家無處藏身」）；
  不可改寫事件性質（如把「計謀被識破」寫成「某人暴露躲藏」）。摘要/變更沒說的因果，不要自行發明。
- **嚴禁發明新實體**：只能描寫地面真相與在場角色中已存在的人、武器、物品、環境（冷兵器酒館不可出現槍、子彈，不可冒出不存在的人物）。
- 貼世界觀基調的語氣寫；後果是質的、會改寫下一步的可能（戰鬥寫傷勢，交涉寫人心向背，潛入寫疑點）。
- **這一拍必須收在一個未決的張力上**（威脅、疑點、抉擇皆可），逼人想回應。
- 節奏隨基調與模式：打鬥可急，交涉可緩可柔，不必都用戰鬥節奏。
- 公開版：只寫全場可見的客觀經過；**標「機密gm」或「僅本人/僅該陣營知」的變更，絕不可寫進公開版**。
- 私密版：只為「察覺到更多」的角色加寫他獨有的感知（如我方才懂的暗號真意）；沒有額外資訊的角色可省略。
- **長度隨份量（時間彈性）**：平淡過場一兩句帶過即可；**有戲的關鍵拍要充分鋪陳成一段**（約 3–6 句），調動上面的「相關狀態與判定、角色性格口吻、場景錨點」，寫出神態、動作、對白、情緒的質感——別每拍都干癟。
- **充分但不杜撰**：可以在已提供的事實上盡情演繹（感官、心理、語氣、節奏），但**所有具體細節都必須源自上面給的材料**（地面真相/相關狀態與判定/狀態變更/角色口吻/場景錨點），不得發明新事實或新實體。

只輸出 JSON：
{{"公開":"全場可見的敘事","私密":{{"char_id":"該角色獨有的額外感知（可選，沒有就不要這個 key）"}}}}"""
    return await grok.call(prompt, Narration, temperature=config.TEMP_NARRATOR, max_tokens=1000)


# ───────────────── 滾動摘要：壓縮舊敘事，保連貫（只管文氣，不記事實） ─────────────────
async def summarize_memory(grok: GrokClient, s: Session, cid: str,
                           old: str, evicted: list) -> str:
    name = s.角色卡[cid].名
    block = "\n".join(evicted)
    prompt = f"""你在維護「{name}」的劇情記憶摘要，供其後續扮演保持連貫。
把【既有摘要】與【接下來發生的數拍】融合成**一段精簡、連貫**的摘要。

# 既有摘要
{old or "（無，這是第一次壓縮）"}

# 新發生的數拍（需併入摘要，之後不再逐字保留）
{block}

# 要求
- 以「{name}」的視角與已知來寫，保留：劇情走向、與各方的關係/恩怨變化、情緒起伏、未解的張力與懸念。
- **不要記錄精確狀態數據**（誰傷在哪、誰站哪、確切承諾——那些另有帳本）；你只負責「故事感」與連貫。
- 精簡，約 120 字內，一段話。

只輸出 JSON：{{"摘要":"..."}}"""
    out = await grok.call(prompt, Summary, temperature=0.4, max_tokens=400)
    return out.摘要


# ───────────────── 帳本整理：合併近義條目、清冗餘（不改變事實） ─────────────────
async def consolidate_conditions(grok: GrokClient, s: Session, label: str,
                                 conds: list) -> list:
    """把一份條目清單裡描述同一件事的近義條目合併成單一條目。回傳整理後的 Condition 清單。"""
    lines = "\n".join(f"- {c.內容}｜gates:{c.gates}｜{c.可見性}" for c in conds)
    prompt = f"""你在整理跑團遊戲的狀態帳本「{label}」，移除冗餘，但**不改變事實**。

下列條目可能有多條描述同一件事的近義條目（例如反覆出現「先還債再談」）。請：
- 把描述同一件事的近義條目**合併成單一精簡條目**；
- 移除已被取代或互相矛盾的舊條目；
- 保留彼此**真正不同**的事實，別把不同的事壓成一條；
- 保留每條的 gates 與可見性；**不要新增**原本沒有的事實。

目前清單：
{lines}

只輸出 JSON：{{"conditions":[{{"內容":"精簡事實","gates":"如何約束後續","可見性":"public"}}]}}"""
    out = await grok.call(prompt, ConsolidateOut, temperature=0.2, max_tokens=900)
    return [Condition(內容=c.內容, gates=c.gates, 可見性=c.可見性, 來源="整理")
            for c in out.conditions]


# ───────────────── 編劇 agent：與使用者協作設計劇本（區塊式編輯） ─────────────────
def _scenario_brief(sc: Scenario) -> str:
    w, L = sc.世界觀, sc.會變層
    lines = [
        f"世界觀：基調={w.基調 or '（空）'}｜法則 {len(w.法則)} 條｜背景{'已寫' if w.背景 else '（空）'}",
        f"場景：地點={sc.scene.地點 or '（空）'}｜鉤子{'已寫' if sc.scene.鉤子 else '（空）'}｜在場={sc.scene.在場 or '（空）'}",
    ]
    if sc.角色卡:
        for cid, c in sc.角色卡.items():
            lines.append(f"角色[{cid}]：{c.名}（{c.陣營}/{c.性別 or '?'}）能力{len(c.能力)}/防禦{len(c.防禦特性)}/弱點{len(c.弱點)}")
    else:
        lines.append("角色：（尚無）")
    lines.append(f"初始局面：已配置角色 {len(L.角色)}｜空間關係{len(L.場景.空間關係)}｜場景事實{len(L.場景.場景事實)}｜社會事實{len(L.場景.社會事實)}")
    return "\n".join(lines)


def author_missing(sc: Scenario) -> list:
    m = []
    if not sc.世界觀.基調:
        m.append("世界觀基調")
    if not sc.scene.地點:
        m.append("場景地點")
    if not sc.scene.鉤子:
        m.append("開場鉤子")
    if not any(c.扮演 == "玩家" for c in sc.角色卡.values()):
        m.append("玩家角色")
    if not any(c.陣營 == "敵" for c in sc.角色卡.values()):
        m.append("至少一個敵人")
    if not sc.會變層.角色:
        m.append("初始局面（姿勢/速度/行動值）")
    return m


async def author_turn(grok: GrokClient, sc: Scenario, history: list, user_msg: str) -> AuthorReply:
    brief = _scenario_brief(sc)
    缺 = "、".join(author_missing(sc)) or "（基本要件看來已齊）"
    hist = "\n".join(f"{r}：{t}" for r, t in history[-6:]) or "（剛開始）"
    在場ids = "、".join(sc.scene.在場) or "（尚無）"
    prompt = f"""你是跑團遊戲的「編劇」，與使用者協作設計一份劇本。你要主動提案、填入具體草稿，而非只問空泛問題。

# 編劇守則（決定品質）
- 角色卡雙用：演戲欄（性格/說話風格/動機目標/行為偏好）＋裁決欄（能力/防禦特性/弱點）；務必補上「性別」與外貌年齡（寫進身分背景），避免被腦補弄錯。
- **把關鍵弱點設成秘密**：放在角色卡「弱點」，並可在會變層用 可見性=gm 埋線索；別讓玩家開局就知道（可被遊戲中發現利用）。
- 世界觀「法則」要能**影響裁決**（例：某類高手刀槍不入、輕功可飛簷走壁、內傷難癒）。
- **埋鉤子與張力**：開場 hook 要逼玩家立刻回應；用場景事實/社會事實提供籌碼與變數（債務、人質、恩怨、出口封死）。
- 會變層初始化：每個在場角色的「姿勢位置、行動速度(玩家7/常5/快6/負傷4)、感知能力」；必要時設「初始行動值」做先機（埋伏者高）；空間關係與場景事實；社會事實。
- 可見性只用：public / gm / faction:陣營 / self:角色id。
- **陣營只用「我方」或「敵」**（玩家與隊友＝我方，對手＝敵；引擎據此判敵我，不可自創如「中立/敵對」）。
- 角色 id 用簡短英文（如 player/aqing/scar）；玩家角色的「扮演」填「玩家」，其餘填「agent」。
- 能力/防禦特性/弱點一律用**質性描述**，**不要寫數值**（寫「舊傷復發時使不上力」而非「行動值-2」）。

# 目前劇本狀態
{brief}
在場角色 id：{在場ids}

# 還缺/待決
{缺}

# 最近對話
{hist}

# 使用者這句話
{user_msg}

# 你的任務（重要）
**優先回應使用者的明確要求**：若要求關於某個角色（名字/性格/能力/弱點/秘密/外貌），就**更新該角色的 char 區塊**（角色卡是劇本核心，別一直延後到「待補」）。沒有特別指向時，挑「還缺/待決」中最關鍵的一項補上（通常是還沒建的角色卡）。
理解使用者意圖，**本回合只更新一個區塊**：
- 區塊="world" → 填 world（World：基調/背景/法則）
- 區塊="scene" → 填 scene（Scene：id/地點/鉤子/在場）
- 區塊="char" → 填 char_id 與 char（一張完整角色卡）
- 區塊="ledger" → 填 ledger（完整初始會變層；**沿用已有的，再加新的**，別漏掉已配置的角色）
- 區塊="none" → 純提問或建議，不更新
把對應區塊的欄位**完整填好**，其餘區塊欄位留 null。reply 簡短說明你做了什麼或要問什麼並引導下一步。
**保留既有內容（重要）**：編輯某區塊時只動使用者要求改的部分，該區塊**其他既有欄位要照原樣一併帶上**（例如只改世界法則時，基調/背景要原樣回傳，別留空）。系統把空欄視為「不更動」，故不必怕，但能帶就帶；ledger 的角色字典只會「更新你給的、保留你沒給的」。
missing 列出還缺的關鍵部分；當「世界觀基調+場景+鉤子+玩家+至少一敵+基本初始局面」齊備時 done=true。

只輸出 JSON（依 schema；未更新的區塊欄位填 null）。"""
    return await grok.call(prompt, AuthorReply, temperature=0.7, max_tokens=2500)
