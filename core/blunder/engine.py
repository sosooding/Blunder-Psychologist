"""Engine seam: deep analysis of individual candidate positions via the C++ wheel.

The C++ engine analyses whole PGNs, but the funnel wants only the candidate positions analysed
deeply. We get that for free: a candidate is turned into a minimal one-move PGN with a ``[FEN]`` /
``[SetUp]`` start position (the C++ parser honours those), so ``analyze_games`` evaluates just that
ply at the requested node budget. This is how the two-pass funnel actually saves compute — only
candidate positions ever reach 2M nodes.

``blunder_engine`` is imported lazily so the rest of core (and its tests) run without the wheel.
Callers depend on the ``Analyzer`` protocol; tests inject a fake.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Protocol

import chess
import chess.pgn

logger = logging.getLogger("blunder.engine")

DEEP_NODES = 2_000_000
SCAN_NODES = 100_000


class EngineUnavailable(RuntimeError):
    """The native blunder_engine wheel could not be imported."""


@dataclass
class DeepResult:
    fen: str
    move_uci: str
    move_san: str
    white_to_move: bool
    eval_cp: int
    best_eval_cp: int
    delta_cp: int  # centipawns lost by the mover (>= 0)
    sharpness: int
    severity: str  # "none" | "inaccuracy" | "mistake" | "blunder"
    archetype: str
    features: dict = field(default_factory=dict)
    best_pv: list[str] = field(default_factory=list)


class Analyzer(Protocol):
    def analyze(
        self, positions: list[tuple[str, str]], *, nodes: int, multipv: int = 3
    ) -> list[DeepResult | None]:
        """Analyse ``(fen_before, move_uci)`` positions; aligned output, ``None`` where dropped."""
        ...


def candidate_pgn(fen_before: str, move_uci: str) -> str:
    """Build a one-move PGN starting from ``fen_before`` (SetUp/FEN headers + the played move)."""
    board = chess.Board(fen_before)
    game = chess.pgn.Game()
    game.setup(board)
    game.add_variation(chess.Move.from_uci(move_uci))
    return str(game)


def _to_dto(mv) -> DeepResult:  # mv: blunder_engine.MoveAnalysis
    try:
        features = json.loads(mv.features) if mv.features else {}
    except (ValueError, TypeError):
        features = {}
    return DeepResult(
        fen=mv.fen,
        move_uci=mv.move_uci,
        move_san=mv.move_san,
        white_to_move=mv.white_to_move,
        eval_cp=mv.eval_cp,
        best_eval_cp=mv.best_eval_cp,
        delta_cp=mv.delta_cp,
        sharpness=mv.sharpness,
        severity=mv.severity,
        archetype=mv.archetype,
        features=features,
        best_pv=list(mv.best_pv),
    )


class EngineAnalyzer:
    """Real analyzer backed by the blunder_engine wheel."""

    def __init__(self, stockfish_path: str = "", engines: int = 1) -> None:
        self._stockfish_path = stockfish_path
        self._engines = engines

    def analyze(
        self, positions: list[tuple[str, str]], *, nodes: int, multipv: int = 3
    ) -> list[DeepResult | None]:
        if not positions:
            return []
        try:
            import blunder_engine  # noqa: PLC0415  (lazy: keep core importable without the wheel)
        except ImportError as exc:  # pragma: no cover - exercised only without the wheel
            raise EngineUnavailable("blunder_engine wheel is not installed") from exc

        pgns = [candidate_pgn(fen, uci) for fen, uci in positions]
        games = blunder_engine.analyze_games(
            pgns, nodes, multipv, self._engines, self._stockfish_path
        )

        # analyze_games preserves input order, but a malformed PGN would be dropped — match back
        # by move UCI (unique per single-move mini-PGN), consuming engine outputs in order.
        by_uci: dict[str, list] = {}
        for ga in games:
            if ga.moves:
                mv = ga.moves[0]
                by_uci.setdefault(mv.move_uci, []).append(mv)

        out: list[DeepResult | None] = []
        for _fen, uci in positions:
            queue = by_uci.get(uci)
            if queue:
                out.append(_to_dto(queue.pop(0)))
            else:
                logger.warning("engine returned no analysis for move %s", uci)
                out.append(None)
        return out


def classify_phase(fen: str) -> str:
    """Coarse game-phase bucket for retrieval filtering: opening / middlegame / endgame."""
    board = chess.Board(fen)
    non_pawn = sum(
        len(board.pieces(pt, color))
        for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
        for color in (chess.WHITE, chess.BLACK)
    )
    if non_pawn <= 6:
        return "endgame"
    if board.fullmove_number <= 12:
        return "opening"
    return "middlegame"


def is_flagged(result: DeepResult) -> bool:
    """Whether a deep result is a recordable blunder (any non-clean severity)."""
    return result.severity not in ("none", "")
