"""Book-exit detection.

A move is "in book" while the position the mover faces is well-represented in the Lichess games
database. ``detect_book_exit`` walks the positions a game passed through and returns the first ply
whose position has fewer than ``threshold`` games in the explorer — that ply is where real play
(and blunder-opportunity counting) begins. If the explorer is unavailable for any queried
position, we fall back to a flat ply (move 10) rather than guess.

``detect_book_exit`` is pure (it takes an ``explorer`` callable); the live, DB-cached explorer is
``CachedExplorer`` below.
"""

import logging
from collections.abc import Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from .lichess import LichessClient, LichessError

logger = logging.getLogger("blunder.book")

DEFAULT_THRESHOLD = 100
DEFAULT_FALLBACK_PLY = 20  # "move 10"

# explorer(fen) -> games-count for that position, or None if the explorer is unavailable.
Explorer = Callable[[str], int | None]


def detect_book_exit(
    fens_before: list[str],
    explorer: Explorer,
    *,
    threshold: int = DEFAULT_THRESHOLD,
    fallback_ply: int = DEFAULT_FALLBACK_PLY,
) -> int:
    """Return the ply index at which the game leaves book.

    ``fens_before[i]`` is the position the mover faces at ply ``i``. Returns the first ``i`` whose
    position has ``< threshold`` games; if every queried position stays in book, returns
    ``len(fens_before)``. If the explorer is unavailable, returns ``min(fallback_ply, len)``.
    """
    for i, fen in enumerate(fens_before):
        count = explorer(fen)
        if count is None:
            return min(fallback_ply, len(fens_before))
        if count < threshold:
            return i
    return len(fens_before)


class CachedExplorer:
    """A DB-cached opening-explorer lookup. Returns the games-count for a FEN, or None if the
    explorer call failed (so the caller can fall back). Caches every successful lookup so repeated
    positions across a user's games cost one HTTP call each."""

    def __init__(self, session: Session, client: LichessClient) -> None:
        self._session = session
        self._client = client

    def __call__(self, fen: str) -> int | None:
        cached = self._session.execute(
            text("SELECT total_games FROM opening_cache WHERE fen = :fen"), {"fen": fen}
        ).scalar_one_or_none()
        if cached is not None:
            return int(cached)

        try:
            data = self._client.opening_explorer(fen)
        except LichessError:
            logger.warning("opening explorer unavailable for fen; falling back", exc_info=True)
            return None

        total = int(data.get("white", 0) + data.get("draws", 0) + data.get("black", 0))
        self._session.execute(
            text(
                "INSERT INTO opening_cache (fen, total_games) VALUES (:fen, :n) "
                "ON CONFLICT (fen) DO UPDATE SET total_games = EXCLUDED.total_games, "
                "fetched_at = now()"
            ),
            {"fen": fen, "n": total},
        )
        self._session.commit()
        return total
