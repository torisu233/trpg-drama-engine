"""劇本路由：CRUD + 編劇 agent 對話（無狀態——前端持有草稿正本）。"""
from fastapi import APIRouter, HTTPException
from ..models import Scenario
from .. import scenario as scen, agents
from ..deps import get_grok

router = APIRouter(prefix="/api", tags=["scenarios / author"])


@router.get("/scenarios")
def list_scenarios():
    return {"scenarios": scen.list_scenarios()}


@router.get("/scenarios/{sid}")
def get_scenario(sid: str):
    try:
        return scen.load_scenario(sid)
    except FileNotFoundError:
        raise HTTPException(404, f"找不到劇本 {sid}")


@router.put("/scenarios/{sid}")
def put_scenario(sid: str, body: Scenario):
    body.id = sid
    p = scen.save_scenario(body)
    return {"ok": True, "id": sid, "path": str(p)}


@router.delete("/scenarios/{sid}")
def delete_scenario(sid: str):
    path = scen.SCENARIOS_DIR / f"{sid}.json"
    if path.exists():
        path.unlink()
        return {"ok": True}
    raise HTTPException(404, f"找不到劇本 {sid}")


@router.post("/author/turn")
async def author_turn(payload: dict):
    """body: {scenario, history:[{role,text}], message}
    回傳合併後的整份劇本 + 回覆（前端直接以 scenario 取代草稿）。"""
    sc = Scenario(**payload.get("scenario", {}))
    history = [(h.get("role", ""), h.get("text", "")) for h in payload.get("history", [])]
    message = payload.get("message", "")
    rep = await agents.author_turn(get_grok(), sc, history, message)
    更新區塊 = scen.apply_author_reply(sc, rep)
    return {
        "reply": rep.reply,
        "scenario": sc,
        "區塊": 更新區塊,
        "char_id": rep.char_id,
        "missing": rep.missing,
        "done": rep.done,
    }
