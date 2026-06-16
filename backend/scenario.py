"""剧本（Scenario）的转换与首次种子导入。

存储已迁到 DB（见 models_db.Scenario）；本模块保留：
- Pydantic 转换：scenario_from_session / session_from_scenario / apply_author_reply（编剧合并）
- seed_demo_scenario：首次（scenarios 表为空）把 武侠001.json 导入为 admin 的已发布剧本
"""
import json
from pathlib import Path
from .models import Scenario, Session, CharLedger
from .models_db import Scenario as DBScenario, User
from . import engine, config

SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "scenarios"   # 仅作首次 seed 来源


def seed_demo_scenario(db) -> None:
    """首次启动（scenarios 表为空）把 武侠001.json 导入 DB（作者=admin、published）。"""
    if db.query(DBScenario.id).first() is not None:
        return
    admin = db.query(User).filter(User.is_admin.is_(True)).first()
    if not admin:
        return
    path = SCENARIOS_DIR / "武侠001.json"
    if not path.exists():
        return
    sc = Scenario(**json.loads(path.read_text(encoding="utf-8")))   # 验证
    db.add(DBScenario(title=sc.id or "武侠001", author_id=admin.id,
                      visibility="published", content=sc.model_dump()))
    db.commit()


def scenario_from_session(s: Session, sid: str) -> Scenario:
    """从 Session 抽出静态/初始数据成 Scenario。"""
    return Scenario(
        id=sid,
        世界观=s.世界观.model_copy(deep=True),
        scene=s.scene.model_copy(deep=True),
        角色卡={k: v.model_copy(deep=True) for k, v in s.角色卡.items()},
        会变层=s.会变层.model_copy(deep=True),
    )


def _nonempty(v) -> bool:
    return v not in (None, "", [], {})


def _merge_fields(existing, new, fields) -> None:
    """逐栏合并：agent 返回空栏视为「不更动」，保留既有值（避免误清空）。"""
    for f in fields:
        nv = getattr(new, f, None)
        if _nonempty(nv):
            setattr(existing, f, nv)


_CARD_FIELDS = ["名", "阵营", "扮演", "性别", "身份背景", "性格", "说话风格",
                "动机目标", "行为偏好", "能力", "防御特性", "弱点"]


def apply_author_reply(sc: Scenario, rep) -> str:
    """把编剧 agent 的区块更新「合并」进剧本正本（空栏＝不更动）。返回更新的区块名。"""
    区 = rep.区块
    if 区 == "world" and rep.world:
        _merge_fields(sc.世界观, rep.world, ["基调", "背景", "法则"])
    elif 区 == "scene" and rep.scene:
        _merge_fields(sc.scene, rep.scene, ["id", "地点", "钩子", "在场"])
    elif 区 == "char" and rep.char and rep.char_id:
        cid = rep.char_id
        if cid in sc.角色卡:
            _merge_fields(sc.角色卡[cid], rep.char, _CARD_FIELDS)
        else:
            sc.角色卡[cid] = rep.char
        if cid not in sc.scene.在场:
            sc.scene.在场.append(cid)
    elif 区 == "ledger" and rep.ledger:
        L = sc.会变层
        for cid, cl in rep.ledger.角色.items():       # key 级合并：保留未提及的角色
            L.角色[cid] = cl
        for f in ["空间关系", "场景事实", "社会事实"]:   # 非空才替换
            nv = getattr(rep.ledger.场景, f)
            if _nonempty(nv):
                setattr(L.场景, f, nv)
        if _nonempty(rep.ledger.阵营私有):
            L.阵营私有.update(rep.ledger.阵营私有)
    else:
        return "none"
    return 区


def session_from_scenario(sc: Scenario) -> Session:
    """把 Scenario 包成全新可玩 Session（深拷贝静态数据，初始化运行期字段）。

    兜底：在场角色缺「初始局面（会变层）」的补默认，否则行动条无人可行动会死循环。
    （玩家身份靠「扮演==玩家」识别，不依赖写死 id，故无需改写角色 id。）
    """
    scene = sc.scene.model_copy(deep=True)
    角色卡 = {k: v.model_copy(deep=True) for k, v in sc.角色卡.items()}
    会变层 = sc.会变层.model_copy(deep=True)

    # 在场角色缺初始局面 → 补默认（玩家略快）
    for cid in scene.在场:
        if cid in 角色卡 and cid not in 会变层.角色:
            spd = config.SPEED_PLAYER if 角色卡[cid].扮演 == "玩家" else config.SPEED_NORMAL
            会变层.角色[cid] = CharLedger(行动速度=spd)

    记忆 = {cid: [] for cid in scene.在场 if cid in 角色卡}
    公开日志, 日志 = [], []
    if scene.地点:
        line = f"【场景】{scene.地点}"
        公开日志.append(line); 日志.append(engine.log_system_entry(line))
    if scene.钩子:
        line = f"【开场】{scene.钩子}"
        公开日志.append(line); 日志.append(engine.log_system_entry(line))
    s = Session(
        scene=scene,
        世界观=sc.世界观.model_copy(deep=True),
        角色卡=角色卡,
        会变层=会变层,
        记忆=记忆,
        公开日志=公开日志,
        日志=日志,
    )
    engine.prune_orphans(s)   # 在场/会变层里引用了不存在角色卡的孤儿 id → 剔除，保证下游 s.角色卡[cid] 安全
    return s
