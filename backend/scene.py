"""手寫場景：雨夜酒館（v1 用，先不做編劇 agent）。

三人局：
- player 玩家（真人）
- aqing 阿青（我方，AI 隊友）
- scar  刀疤（敵，AI）

埋的秘密（gm 可見性，玩家/隊友不知道）：
- 刀疤怕火
- 刀疤在等同夥從外包抄
"""
from .models import (
    Session, Scene, CharCard, Ledger, CharLedger, SceneLedger, Condition, Item,
)
from . import config


def new_tavern_session() -> Session:
    scene = Scene(
        id="tavern",
        地點="雨夜酒館，爐火將熄，後門通向馬廄",
        鉤子="刀疤一手按在刀柄上，慢悠悠開口：「聽說你欠漕幫的錢，今晚想怎麼還？」",
        在場=["player", "aqing", "scar"],
    )

    角色卡 = {
        "player": CharCard(
            名="玩家", 陣營="我方", 扮演="玩家",
            背景="流亡的前禁軍校尉，欠下漕幫一筆債。",
            性格=["謹慎", "記仇"],
            能力=["擅長近身短刃", "會看人說謊"],
        ),
        "aqing": CharCard(
            名="阿青", 陣營="我方", 扮演="agent",
            背景="與玩家同行的江湖混混，講義氣但魯莽。",
            性格=["魯莽", "重情義", "嘴賤"],
            能力=["力氣大", "會掀桌砸場"],
        ),
        "scar": CharCard(
            名="刀疤", 陣營="敵", 扮演="agent",
            背景="漕幫打手，臉上一道刀疤，奉命來討債或要人。",
            性格=["狡猾", "記仇", "愛拖時間"],
            能力=["擅長近身短刀", "會看人說謊"],
        ),
    }

    會變層 = Ledger(
        角色={
            "player": CharLedger(
                姿勢位置="坐在角落桌旁，背對牆",
                物品={
                    "dagger": Item(名="短刃", 類型="武器", 固有性質=["鋒利"],
                                   狀態="完好", 位置="藏在披風下"),
                },
                行動速度=config.SPEED_PLAYER,
                感知能力="正常",
                行動值=0,
            ),
            "aqing": CharLedger(
                姿勢位置="站在玩家身側",
                物品={},
                行動速度=config.SPEED_NORMAL,
                感知能力="正常",
                行動值=0,
            ),
            "scar": CharLedger(
                姿勢位置="背靠吧台站立，俯視這桌",
                物品={
                    "knife": Item(名="短刀", 類型="武器", 固有性質=["刃利"],
                                  狀態="完好", 位置="右手按在刀柄"),
                },
                身心狀況=[],
                特殊情況=[],
                # 埋的秘密：gm 可見性，玩家/隊友看不到
                隨身=[
                    Condition(內容="怕火", gates="見明火會本能退縮", 可見性="gm",
                              來源="劇本預設", 生命週期="永久"),
                ],
                行動速度=config.SPEED_NORMAL,
                感知能力="正常",
                行動值=0,
            ),
        },
        場景=SceneLedger(
            空間關係=[
                Condition(內容="刀疤背靠吧台", gates="防背後偷襲、退路受吧台限制",
                          可見性="public"),
                Condition(內容="玩家背對牆坐在角落", gates="背後安全，但被堵則無退路",
                          可見性="public"),
            ],
            場景事實=[
                Condition(內容="後門上鎖，唯一出口是前門", 可見性="public"),
                Condition(內容="桌上有油燈，爐火將熄", gates="可取火源", 可見性="public"),
                Condition(內容="刀疤其實在等同夥從外包抄", 可見性="gm",
                          來源="劇本預設"),
            ],
        ),
        陣營私有={"我方": {"計策": []}},
    )

    return Session(
        scene=scene,
        角色卡=角色卡,
        會變層=會變層,
        記憶={"aqing": [], "scar": [], "player": []},
        公開日誌=[f"【場景】{scene.地點}", f"【開場】{scene.鉤子}"],
    )
