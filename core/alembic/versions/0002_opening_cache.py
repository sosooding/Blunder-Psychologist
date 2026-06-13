"""opening explorer cache

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-13

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "opening_cache",
        sa.Column("fen", sa.Text(), primary_key=True),
        sa.Column("total_games", sa.BigInteger(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("opening_cache")
