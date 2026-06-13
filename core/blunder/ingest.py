"""Parse Lichess game records into per-ply data, and upsert game rows (deduped by lichess id).

A Lichess NDJSON record carries structured metadata *and* the full PGN (``pgnInJson=true``).
We take id/speed/players/timestamps from the JSON (reliable) and read per-move clocks and
embedded ``[%eval]`` straight out of the PGN with python-chess. Evals are normalised to
centipawns from White's perspective (mate mapped to ±10000) — the same convention the C++ engine
emits, so the cheap and deep passes speak one language.
"""

import io
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import chess
import chess.pgn
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("blunder.ingest")

_MATE_CP = 10000


@dataclass
class ParsedMove:
    ply: int  # 0-based ply index
    fen_before: str  # position the mover faced — the FEN we analyse
    san: str
    uci: str
    color: bool  # chess.WHITE / chess.BLACK of the mover
    is_user_move: bool
    eval_cp: int | None  # White-POV centipawns of the *resulting* position, from [%eval]
    clock_seconds: int | None


@dataclass
class ParsedGame:
    lichess_id: str
    pgn: str
    time_control: str | None
    played_at: datetime | None
    speed: str | None
    user_color: bool | None  # which colour the profiled user played, or None if undetermined
    moves: list[ParsedMove]


_SITE_ID = re.compile(r"lichess\.org/(\w{8})")
_SPEEDS = ("ultrabullet", "bullet", "blitz", "rapid", "classical", "correspondence")


def _user_color_from_headers(headers: "chess.pgn.Headers", username: str) -> bool | None:
    u = username.lower()
    if (headers.get("White") or "").lower() == u:
        return chess.WHITE
    if (headers.get("Black") or "").lower() == u:
        return chess.BLACK
    return None


def _lichess_id_from_site(site: str | None) -> str:
    m = _SITE_ID.search(site or "")
    return m.group(1) if m else ""


def _speed_from_event(event: str | None) -> str | None:
    e = (event or "").lower()
    return next((s for s in _SPEEDS if s in e), None)


def _played_at_from_headers(date_str: str | None, time_str: str | None) -> datetime | None:
    if not date_str or "?" in date_str:
        return None
    try:
        dt = datetime.strptime(f"{date_str} {time_str or '00:00:00'}", "%Y.%m.%d %H:%M:%S")
    except ValueError:
        return None
    return dt.replace(tzinfo=UTC)


def parse_pgn(pgn: str, username: str) -> ParsedGame:
    """Parse a stored Lichess PGN into a ParsedGame, deriving everything from the PGN itself.

    Used when re-parsing games already persisted (scan/deep passes), where only the PGN is kept.
    """
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        raise ValueError("could not parse PGN")

    h = game.headers
    user_color = _user_color_from_headers(h, username)
    tc = h.get("TimeControl")

    board = game.board()
    moves: list[ParsedMove] = []
    for ply, node in enumerate(game.mainline()):
        mover = board.turn
        fen_before = board.fen()
        san = board.san(node.move)
        board.push(node.move)

        pov = node.eval()
        eval_cp = pov.white().score(mate_score=_MATE_CP) if pov is not None else None
        clk = node.clock()
        clock_seconds = int(clk) if clk is not None else None

        moves.append(
            ParsedMove(
                ply=ply,
                fen_before=fen_before,
                san=san,
                uci=node.move.uci(),
                color=mover,
                is_user_move=(user_color is not None and mover == user_color),
                eval_cp=eval_cp,
                clock_seconds=clock_seconds,
            )
        )

    if user_color is None:
        logger.warning(
            "could not determine %r's colour in game %s; no user moves will be scanned",
            username,
            h.get("Site"),
        )

    return ParsedGame(
        lichess_id=_lichess_id_from_site(h.get("Site")),
        pgn=pgn,
        time_control=tc if tc and tc != "-" else None,
        played_at=_played_at_from_headers(h.get("UTCDate"), h.get("UTCTime")),
        speed=_speed_from_event(h.get("Event")),
        user_color=user_color,
        moves=moves,
    )


def parse_game(record: dict[str, Any], username: str) -> ParsedGame:
    """Parse one NDJSON game record, enriching the PGN parse with the richer JSON metadata."""
    pg = parse_pgn(record["pgn"], username)

    if record.get("id"):
        pg.lichess_id = record["id"]
    if record.get("speed"):
        pg.speed = record["speed"]
    clock = record.get("clock")
    if clock and "initial" in clock:
        pg.time_control = f"{clock['initial']}+{clock.get('increment', 0)}"
    if record.get("createdAt") is not None:
        pg.played_at = datetime.fromtimestamp(record["createdAt"] / 1000, tz=UTC)
    return pg


# -- persistence -------------------------------------------------------------------------

def upsert_user(session: Session, username: str) -> int:
    """Get-or-create a user row, returning its id. Username is stored as-given."""
    row = session.execute(
        text(
            "INSERT INTO users (lichess_username) VALUES (:u) "
            "ON CONFLICT (lichess_username) DO UPDATE "
            "SET lichess_username = EXCLUDED.lichess_username "
            "RETURNING id"
        ),
        {"u": username},
    ).one()
    session.commit()
    return int(row[0])


def upsert_game(session: Session, user_id: int, pg: ParsedGame) -> tuple[int, bool]:
    """Insert the game if new (deduped on lichess_id). Return (game_id, created)."""
    row = session.execute(
        text(
            "INSERT INTO games "
            "(user_id, lichess_id, pgn, time_control, played_at, analysis_status) "
            "VALUES (:uid, :lid, :pgn, :tc, :pa, 'pending') "
            "ON CONFLICT (lichess_id) DO NOTHING RETURNING id"
        ),
        {
            "uid": user_id,
            "lid": pg.lichess_id,
            "pgn": pg.pgn,
            "tc": pg.time_control,
            "pa": pg.played_at,
        },
    ).fetchone()
    if row is not None:
        session.commit()
        return int(row[0]), True

    existing = session.execute(
        text("SELECT id FROM games WHERE lichess_id = :lid"), {"lid": pg.lichess_id}
    ).scalar_one()
    session.commit()
    return int(existing), False
