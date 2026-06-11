"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-06-10

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("lichess_username", sa.Text(), nullable=False),
        sa.Column("last_synced_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("lichess_username", name="uq_users_username"),
    )

    op.create_table(
        "games",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("lichess_id", sa.Text(), nullable=True),
        sa.Column("pgn", sa.Text(), nullable=False),
        sa.Column("time_control", sa.Text(), nullable=True),
        sa.Column("played_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("book_exit_ply", sa.Integer(), nullable=True),
        sa.Column("analysis_status", sa.Text(), nullable=False, server_default="pending"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("lichess_id", name="uq_games_lichess_id"),
    )
    op.create_index("ix_games_user_id", "games", ["user_id"])

    op.create_table(
        "move_analyses",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("game_id", sa.BigInteger(), nullable=False),
        sa.Column("ply", sa.Integer(), nullable=False),
        sa.Column("fen", sa.Text(), nullable=False),
        sa.Column("move", sa.Text(), nullable=False),
        sa.Column("eval_cp", sa.Integer(), nullable=True),
        sa.Column("best_eval_cp", sa.Integer(), nullable=True),
        sa.Column("delta_cp", sa.Integer(), nullable=True),
        sa.Column("sharpness", sa.Double(), nullable=True),
        sa.Column("clock_seconds", sa.Integer(), nullable=True),
        sa.Column("phase", sa.Text(), nullable=True),
        sa.Column("pawn_archetype", sa.Text(), nullable=True),
        sa.Column("features", postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("game_id", "ply", name="uq_move_analyses_game_ply"),
    )
    op.create_index("ix_move_analyses_game_id", "move_analyses", ["game_id"])

    op.create_table(
        "blunders",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("move_analysis_id", sa.BigInteger(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("motif_tags", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("annotation", sa.Text(), nullable=True),
        sa.Column("embedding_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["move_analysis_id"], ["move_analyses.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_blunders_move_analysis_id", "blunders", ["move_analysis_id"])

    op.create_table(
        "profiles",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("stats", postgresql.JSONB(), nullable=True),
        sa.Column("narrative", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "version", name="uq_profiles_user_version"),
    )
    op.create_index("ix_profiles_user_id", "profiles", ["user_id"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status in ('pending','running','done','failed','dead')",
            name="ck_jobs_status",
        ),
    )
    op.create_index(
        "ix_jobs_claim",
        "jobs",
        ["priority", "created_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_table("profiles")
    op.drop_table("blunders")
    op.drop_table("move_analyses")
    op.drop_table("games")
    op.drop_table("users")
