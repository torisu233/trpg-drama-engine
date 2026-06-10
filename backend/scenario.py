"""剧本（Scenario）的访问与转换。

Scenario = 剧本的静态/初始数据（世界观+scene+角色卡+初始会变层）。
- list/load/save_scenario：scenarios/*.json 的列出、读、写
- scenario_from_session：从一个 Session 抽出 Scenario（用来把手写场景导出成种子）
- session_from_scenario：把 Scenario 包成可玩的 Session（初始化运行期字段）
"""
import json
from pathlib import Path
from typing import List
from .models import Scenario, Session

SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "scenarios"


def list_scenarios() -> List[str]:
    if not SCENARIOS_DIR.exists():
        return []
    return sorted(p.stem for p in SCENARIOS_DIR.glob("*.json"))


def load_scenario(name: str) -> Scenario:
    path = SCENARIOS_DIR / f"{name}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return Scenario(**data)


def save_scenario(scenario: Scenario) -> Path:
    SCENARIOS_DIR.mkdir(exist_ok=True)
    path = SCENARIOS_DIR / f"{scenario.id}.json"
    path.write_text(scenario.model_dump_json(indent=2), encoding="utf-8")
    return path


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
    """逐栏合并：agent 回传空栏视为「不更动」，保留既有值（避免误清空）。"""
    for f in fields:
        nv = getattr(new, f, None)
        if _nonempty(nv):
            setattr(existing, f, nv)


_CARD_FIELDS = ["名", "阵营", "扮演", "性别", "身分背景", "性格", "说话风格",
                "动机目标", "行为偏好", "能力", "防御特性", "弱点"]


def apply_author_reply(sc: Scenario, rep) -> str:
    """把编剧 agent 的区块更新「合并」进剧本正本（空栏＝不更动）。回传更新的区块名。"""
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
    """把 Scenario 包成全新可玩 Session（深拷贝静态数据，初始化运行期字段）。"""
    记忆 = {cid: [] for cid in sc.scene.在场}
    公开日志 = []
    if sc.scene.地点:
        公开日志.append(f"【场景】{sc.scene.地点}")
    if sc.scene.钩子:
        公开日志.append(f"【开场】{sc.scene.钩子}")
    return Session(
        scene=sc.scene.model_copy(deep=True),
        世界观=sc.世界观.model_copy(deep=True),
        角色卡={k: v.model_copy(deep=True) for k, v in sc.角色卡.items()},
        会变层=sc.会变层.model_copy(deep=True),
        记忆=记忆,
        公开日志=公开日志,
    )
