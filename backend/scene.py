"""手写场景：雨夜酒馆（武侠世界观，v1 用，先不做编剧 agent）。

三人局：
- player player（真人）
- aqing 阿青（ally，AI 队友）
- scar  刀疤（enemy，AI）

示范三件事：
- 世界观法则（含「武功大成者刀枪不入」这类影响裁决的硬规则）
- 角色卡的演戏特质 + 裁决特质（防御/weaknesses，对手看不到，可被发现利用）
- 埋的秘密（刀疤怕火＝weaknesses；在等同伙包抄＝gm scene_facts）
"""
from .models import (
    Session, Scene, World, CharCard, Ledger, CharLedger, SceneLedger, Condition, Item,
)
from . import config


def new_tavern_session() -> Session:
    world = World(
        tone="武侠。江湖恩怨、刀光剑影，重义轻生死，市井与庙堂交错。",
        background=(
            "这是个武林门派林立的年代。漕帮把持运河命脉，黑白通吃；"
            "江湖人讲的是面子、义气与恩仇。武功分高下：练到家的高手气劲护体，"
            "寻常兵刃难伤分毫，唯有更高明的手段才动得了他。钱与命，在江湖上常常等价。"
        ),
        laws=[
            "武功大成者运气护体，寻常刀剑拳脚难伤其要害；须以更强内力、毒、火攻、点中要穴、"
            "出其不意攻其弱点，或断其根基（废其武功来源）方能制之。",
            "轻功高者可飞檐走壁、瞬间欺近或脱身；轻功低者追之不及。",
            "内伤重于外伤，且难以速愈；中毒、点穴会在数招内逐步发作。",
            "以势压人有时胜过动手：威望、把柄、人质可不战而屈人之兵。",
        ],
    )

    cards = {
        "player": CharCard(
            name="player", faction="ally", controller="player", gender="男",
            backstory="流亡的前禁军校尉，三十出头，身形精悍、左肩有旧伤；因故欠下漕帮一笔债，剑法出身行伍。",
            personality=["谨慎", "记仇"],
            voice="话不多，冷硬，必要时才开口。",
            motive="活着脱身，并查清这笔债背后是谁要你的命。",
            tactics=["先观察再出手", "擅用环境", "不打无把握之仗"],
            abilities=["行伍剑法，近身狠准", "识破谎言", "临阵冷静"],
            defenses=["久经战阵，不易自乱阵脚"],
            weaknesses=["旧伤在左肩，受力过猛会使不上劲"],
        ),
        "aqing": CharCard(
            name="阿青", faction="ally", controller="agent", gender="男",
            backstory="与玩家同行的市井混混，二十来岁的精壮汉子、嗓门奇大；帮过你一把，自此认你做大哥。",
            personality=["鲁莽", "重情义", "嘴贱"],
            voice="大嗓门、粗话连篇、爱起哄，紧张时更聒噪。",
            motive="罩着大哥（player）全身而退，顺便逞点威风。",
            tactics=["先动手再说", "掀桌砸场、制造混乱", "拿身边杂物当武器"],
            abilities=["力气大", "市井打斗、不要命", "对酒馆地形熟"],
            defenses=["皮粗肉厚，挨几下还能撑"],
            weaknesses=["头脑简单，容易被激将或诓骗", "护主心切，会为玩家涉险"],
        ),
        "scar": CharCard(
            name="刀疤", faction="enemy", controller="agent", gender="男",
            backstory="漕帮的二路打手，四十岁精瘦汉子，左脸一道刀疤；奉命来讨债兼拿人。",
            personality=["狡猾", "记仇", "欺软怕硬"],
            voice="皮笑肉不笑、爱抛狠话又留余地，惯于拖延套话。",
            motive="拖到同伙包抄合围，再一举拿下玩家，最好不伤自己。",
            tactics=["能拖就拖、虚与委蛇", "占上风才动手", "以人质/把柄要挟"],
            abilities=["漕帮快刀，近身狠辣", "看人说谎、见风转舵"],
            defenses=["练过横练功夫，皮糙肉厚，寻常拳脚难伤"],
            weaknesses=[
                "怕火（幼年火劫留下的阴影，见明火会本能退缩）",   # 秘密：对手看不到角色卡
                "贪功怕死，局势一坏就先保命",
            ],
        ),
    }

    ledger = Ledger(
        characters={
            "player": CharLedger(
                posture="坐在角落桌旁，背对墙",
                items={"dagger": Item(name="短刃", kind="武器", traits=["锋利"],
                                     state="intact", location="藏在披风下")},
                speed=config.SPEED_PLAYER, perception="normal", gauge=0,
            ),
            "aqing": CharLedger(
                posture="站在玩家身侧",
                speed=config.SPEED_NORMAL, perception="normal", gauge=0,
            ),
            "scar": CharLedger(
                posture="背靠吧台站立，俯视这桌",
                items={"knife": Item(name="快刀", kind="武器", traits=["刃利", "出鞘快"],
                                    state="intact", location="右手按在刀柄")},
                speed=config.SPEED_NORMAL, perception="normal", gauge=0,
            ),
        },
        scene=SceneLedger(
            spatial=[
                Condition(content="刀疤背靠吧台", gates="防背后偷袭、退路受吧台限制", visibility="public"),
                Condition(content="玩家背对墙坐在角落", gates="背后安全，但被堵则无退路", visibility="public"),
            ],
            scene_facts=[
                Condition(content="后门上锁，唯一出口是前门", visibility="public"),
                Condition(content="桌上有油灯，炉火将熄", gates="可取火源（明火）", visibility="public"),
                Condition(content="刀疤其实在等同伙从外包抄，约数招内可到", visibility="gm", source="scenario"),
            ],
            social_facts=[
                Condition(content="玩家欠漕帮一笔债，刀疤奉命来讨", gates="刀疤师出有名；还清或翻脸皆改变局面",
                          visibility="public", source="scenario"),
            ],
        ),
        faction_private={"ally": {"plans": []}},
    )

    return Session(
        scene=Scene(
            id="tavern",
            location="雨夜酒馆，炉火将熄，后门通向马厩",
            hook="刀疤一手按在刀柄上，慢悠悠开口：「听说你欠漕帮的钱，今晚想怎么还？」",
            present=["player", "aqing", "scar"],
        ),
        world=world,
        cards=cards,
        ledger=ledger,
        memory={"aqing": [], "scar": [], "player": []},
        public_log=["【scene】雨夜酒馆，炉火将熄，后门通向马厩",
                  "【开场】刀疤一手按在刀柄上，慢悠悠开口：「听说你欠漕帮的钱，今晚想怎么还？」"],
    )
