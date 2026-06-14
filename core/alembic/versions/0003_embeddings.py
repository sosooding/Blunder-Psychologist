"""blunder embeddings (for FAISS rebuilds)

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-14

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Source of truth for vectors so a per-user FAISS index can be rebuilt without re-embedding.
    op.create_table(
        "embeddings",
        sa.Column("blunder_id", sa.BigInteger(), primary_key=True),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column("vector", sa.LargeBinary(), nullable=False),  # float32 bytes, L2-normalized
        sa.ForeignKeyConstraint(["blunder_id"], ["blunders.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("embeddings")
