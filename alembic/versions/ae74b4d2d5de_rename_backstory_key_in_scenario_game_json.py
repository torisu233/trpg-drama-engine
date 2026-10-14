"""rename backstory key in scenario/game json (historical; now a no-op)

Revision ID: ae74b4d2d5de
Revises: f159fc1ec85e
Create Date: 2026-06-15 10:01:06.786615

Historically this was a data migration that renamed one character-card key inside the
scenarios.content / games.state JSON documents (an older spelling of the backstory field).
It has been superseded by the English schema: every field now has its English name, and
fresh databases never contain the old key. upgrade()/downgrade() are therefore no-ops,
kept only so the revision chain stays intact.
"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = 'ae74b4d2d5de'
down_revision: Union[str, Sequence[str], None] = 'f159fc1ec85e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op: the historical key rename is superseded by the English schema."""
    pass


def downgrade() -> None:
    """No-op: nothing to undo."""
    pass
