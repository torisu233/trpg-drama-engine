"""rename shenfen key in scenario/game json

Revision ID: ae74b4d2d5de
Revises: f159fc1ec85e
Create Date: 2026-06-15 10:01:06.786615

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ae74b4d2d5de'
down_revision: Union[str, Sequence[str], None] = 'f159fc1ec85e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 用 Python 解析 dict 改键，而非 SQL 文本 REPLACE：
# json 列默认以 \uXXXX 转义存中文，文本 REPLACE 匹配不到字面中文；psycopg2 读出来已是 dict，免疫转义。
_TABLES = (("scenarios", "content"), ("games", "state"))


def _rename_card_key(doc, old: str, new: str) -> bool:
    cards = (doc or {}).get("角色卡")
    if not isinstance(cards, dict):
        return False
    changed = False
    for card in cards.values():
        if isinstance(card, dict) and old in card and new not in card:
            card[new] = card.pop(old)
            changed = True
    return changed


def _migrate(old: str, new: str) -> None:
    conn = op.get_bind()
    for table, col in _TABLES:
        for rid, doc in conn.execute(sa.text(f"SELECT id, {col} FROM {table}")).fetchall():
            if isinstance(doc, str):
                doc = json.loads(doc)
            if _rename_card_key(doc, old, new):
                conn.execute(
                    sa.text(f"UPDATE {table} SET {col} = CAST(:d AS json) WHERE id = :id"),
                    {"d": json.dumps(doc, ensure_ascii=False), "id": rid})


def upgrade() -> None:
    """已入库的 scenarios.content / games.state 里 角色卡 的键 身分背景 → 身份背景（台→陆用词）。"""
    _migrate("身分背景", "身份背景")


def downgrade() -> None:
    _migrate("身份背景", "身分背景")
