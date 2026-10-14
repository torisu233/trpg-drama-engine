"""剧本（Scenario）的转换。

存储全在 DB（见 models_db.Scenario）；本模块只管 Pydantic 转换：
scenario_from_session / session_from_scenario / apply_author_reply（编剧合并）。
DB 初始化不再注入任何示范剧本——剧本一律由用户经编剧页/接口创建后存 DB。
"""
from .models import Scenario, Session, CharLedger
from . import engine, config


def scenario_from_session(s: Session, sid: str) -> Scenario:
    """从 Session 抽出静态/初始数据成 Scenario。"""
    return Scenario(
        id=sid,
        world=s.world.model_copy(deep=True),
        scene=s.scene.model_copy(deep=True),
        cards={k: v.model_copy(deep=True) for k, v in s.cards.items()},
        ledger=s.ledger.model_copy(deep=True),
    )


def _nonempty(v) -> bool:
    return v not in (None, "", [], {})


def _merge_fields(existing, new, fields) -> None:
    """逐栏合并：agent 返回空栏视为「不更动」，保留既有值（避免误清空）。"""
    for f in fields:
        nv = getattr(new, f, None)
        if _nonempty(nv):
            setattr(existing, f, nv)


# 故意不含「directive」——它是用户手填的最高优先级铁律，AI 编剧不得碰（既有角色合并时保留、不被清）
_CARD_FIELDS = ["name", "faction", "controller", "gender", "backstory", "personality", "voice",
                "motive", "tactics", "abilities", "defenses", "weaknesses"]


def apply_author_reply(sc: Scenario, rep) -> str:
    """把编剧 agent 的区块更新「合并」进剧本正本（空栏＝不更动）。返回更新的区块名。"""
    区 = rep.block
    if 区 == "world" and rep.world:
        _merge_fields(sc.world, rep.world, ["tone", "background", "laws"])
    elif 区 == "scene" and rep.scene:
        _merge_fields(sc.scene, rep.scene, ["id", "location", "hook", "present"])
    elif 区 == "char" and rep.char and rep.char_id:
        cid = rep.char_id
        if cid in sc.cards:
            _merge_fields(sc.cards[cid], rep.char, _CARD_FIELDS)
        else:
            sc.cards[cid] = rep.char
        if cid not in sc.scene.present:
            sc.scene.present.append(cid)
    elif 区 == "ledger" and rep.ledger:
        L = sc.ledger
        for cid, cl in rep.ledger.characters.items():       # key 级合并：保留未提及的角色
            L.characters[cid] = cl
        for f in ["spatial", "scene_facts", "social_facts"]:   # 非空才替换
            nv = getattr(rep.ledger.scene, f)
            if _nonempty(nv):
                setattr(L.scene, f, nv)
        if _nonempty(rep.ledger.faction_private):
            L.faction_private.update(rep.ledger.faction_private)
    else:
        return "none"
    return 区


def session_from_scenario(sc: Scenario) -> Session:
    """把 Scenario 包成全新可玩 Session（深拷贝静态数据，初始化运行期字段）。

    兜底：在场角色缺「初始局面（ledger）」的补默认，否则行动条无人可行动会死循环。
    （玩家身份靠「controller==player」识别，不依赖写死 id，故无需改写角色 id。）
    """
    scene = sc.scene.model_copy(deep=True)
    cards = {k: v.model_copy(deep=True) for k, v in sc.cards.items()}
    ledger = sc.ledger.model_copy(deep=True)

    # 在场角色缺初始局面 → 补默认（玩家略快）
    for cid in scene.present:
        if cid in cards and cid not in ledger.characters:
            spd = config.SPEED_PLAYER if cards[cid].controller == "player" else config.SPEED_NORMAL
            ledger.characters[cid] = CharLedger(speed=spd)

    memory = {cid: [] for cid in scene.present if cid in cards}
    public_log, log = [], []
    if scene.location:
        line = f"【scene】{scene.location}"
        public_log.append(line); log.append(engine.log_system_entry(line))
    if scene.hook:
        line = f"【开场】{scene.hook}"
        public_log.append(line); log.append(engine.log_system_entry(line))
    s = Session(
        scene=scene,
        world=sc.world.model_copy(deep=True),
        cards=cards,
        ledger=ledger,
        memory=memory,
        public_log=public_log,
        log=log,
    )
    engine.prune_orphans(s)   # present/会变层里引用了不存在角色卡的孤儿 id → 剔除，保证下游 s.cards[cid] 安全
    return s
