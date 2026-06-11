from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    CheckConstraint,
    Double,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    lichess_username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    games: Mapped[list["Game"]] = relationship(back_populates="user")
    profiles: Mapped[list["Profile"]] = relationship(back_populates="user")


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # External Lichess game id, for dedup on (re)ingestion. Not in the original design
    # sketch but required in practice; populated from Phase 3.
    lichess_id: Mapped[str | None] = mapped_column(Text, unique=True)
    pgn: Mapped[str] = mapped_column(Text, nullable=False)
    time_control: Mapped[str | None] = mapped_column(Text)
    played_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    book_exit_ply: Mapped[int | None] = mapped_column(Integer)
    analysis_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="pending"
    )

    user: Mapped["User"] = relationship(back_populates="games")
    move_analyses: Mapped[list["MoveAnalysis"]] = relationship(back_populates="game")


class MoveAnalysis(Base):
    __tablename__ = "move_analyses"
    __table_args__ = (
        UniqueConstraint("game_id", "ply", name="uq_move_analyses_game_ply"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ply: Mapped[int] = mapped_column(Integer, nullable=False)
    fen: Mapped[str] = mapped_column(Text, nullable=False)
    move: Mapped[str] = mapped_column(Text, nullable=False)
    eval_cp: Mapped[int | None] = mapped_column(Integer)
    best_eval_cp: Mapped[int | None] = mapped_column(Integer)
    delta_cp: Mapped[int | None] = mapped_column(Integer)
    sharpness: Mapped[float | None] = mapped_column(Double)
    clock_seconds: Mapped[int | None] = mapped_column(Integer)
    phase: Mapped[str | None] = mapped_column(Text)
    pawn_archetype: Mapped[str | None] = mapped_column(Text)
    features: Mapped[dict | None] = mapped_column(JSONB)

    game: Mapped["Game"] = relationship(back_populates="move_analyses")
    blunder: Mapped["Blunder | None"] = relationship(
        back_populates="move_analysis", uselist=False
    )


class Blunder(Base):
    __tablename__ = "blunders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    move_analysis_id: Mapped[int] = mapped_column(
        ForeignKey("move_analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    motif_tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}"
    )
    annotation: Mapped[str | None] = mapped_column(Text)
    embedding_id: Mapped[int | None] = mapped_column(BigInteger)

    move_analysis: Mapped["MoveAnalysis"] = relationship(back_populates="blunder")


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (
        UniqueConstraint("user_id", "version", name="uq_profiles_user_version"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    stats: Mapped[dict | None] = mapped_column(JSONB)
    narrative: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="profiles")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending','running','done','failed','dead')",
            name="ck_jobs_status",
        ),
        Index(
            "ix_jobs_claim",
            "priority",
            "created_at",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="10")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
