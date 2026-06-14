"""persist best_pv on move_analyses (for annotation + plan explainer)

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-14

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Engine's best line (UCI). Needed by the positional motif detectors (played-vs-best diff) and
    # by the Phase 5 Plan Explainer, neither of which re-runs the engine.
    op.add_column("move_analyses", sa.Column("best_pv", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("move_analyses", "best_pv")
