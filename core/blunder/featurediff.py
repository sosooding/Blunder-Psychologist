"""Played-vs-best positional feature diffing.

Given the position the mover faced (``fen_before``), the move they played, and the engine's best
move, extract the feature vector of each *resulting* position — both from the mover's perspective —
and diff them field by field. This is the shared machinery behind the positional motif detectors
(Phase 4) and the Plan Explainer's PV narration (Phase 5): the LLM only ever narrates these
computed deltas, never free-associates.

The feature direction is field-dependent, so we expose the raw ``played - best`` delta and let each
detector decide what counts as damage: more isolated/doubled/backward pawns or king-zone attackers
is worse, while less mobility/space/passed-pawns/king-shield is worse.
"""

from dataclasses import dataclass

import chess

from .engine import FeatureExtractor

# Numeric fields emitted by the C++ extractor (``archetype`` is the one non-numeric field).
NUMERIC_FIELDS = (
    "isolated_pawns",
    "doubled_pawns",
    "backward_pawns",
    "passed_pawns",
    "open_files",
    "half_open_files",
    "king_shield",
    "king_zone_attackers",
    "space",
    "mobility",
)


@dataclass
class FeatureDiff:
    played: dict  # features after the played move (mover's perspective)
    best: dict  # features after the engine's best move (mover's perspective)
    delta: dict  # played[k] - best[k] for each numeric field

    @property
    def played_archetype(self) -> str:
        return self.played.get("archetype", "unknown")

    @property
    def best_archetype(self) -> str:
        return self.best.get("archetype", "unknown")


def push_uci(fen_before: str, uci: str) -> str:
    """Return the FEN of the position after playing ``uci`` from ``fen_before``."""
    board = chess.Board(fen_before)
    board.push(chess.Move.from_uci(uci))
    return board.fen()


def feature_diff(
    fen_before: str,
    played_uci: str,
    best_uci: str,
    *,
    mover_white: bool,
    extractor: FeatureExtractor,
) -> FeatureDiff:
    """Diff the positions resulting from the played move vs the engine's best move.

    Both resulting positions are scored from the mover's perspective (``mover_white``), so the
    delta isolates what the played move conceded relative to the best alternative.
    """
    played = extractor.extract(push_uci(fen_before, played_uci), white_perspective=mover_white)
    best = extractor.extract(push_uci(fen_before, best_uci), white_perspective=mover_white)
    delta = {k: played.get(k, 0) - best.get(k, 0) for k in NUMERIC_FIELDS}
    return FeatureDiff(played=played, best=best, delta=delta)
