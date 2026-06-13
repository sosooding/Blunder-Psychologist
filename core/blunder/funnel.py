"""The cheap pass of the two-pass funnel.

Scope: the profiled user's moves, post-book. Where Lichess embedded evals exist we threshold the
eval loss directly (free, no engine). User moves that lack the evals needed to compute a loss are
returned separately so the orchestrator can run the ~100k-node engine fallback on just those FENs.

Loss is in centipawns from the *mover's* perspective (positive = the move worsened their position).
A move is a candidate when its loss clears ``threshold``. Positions already decided before the
move (|eval| > ``decided_cp``) are skipped — the same suppression the Phase-2 severity classifier
applies, since swings in won/lost positions are not diagnostic of a characteristic weakness.
"""

from dataclasses import dataclass

import chess

from .ingest import ParsedMove

CHEAP_DELTA_THRESHOLD = 100  # cp; generous on purpose — the deep pass + severity refine
DECIDED_CP = 600  # cp; pre-move |eval| above this means the game is already decided


@dataclass
class Candidate:
    ply: int
    loss_cp: int
    source: str  # "lichess_eval" or "engine_scan"


def loss_cp(eval_before: int, eval_after: int, color: bool) -> int:
    """Mover-perspective loss in centipawns from White-POV evals (positive = position worsened)."""
    if color == chess.WHITE:
        return eval_before - eval_after
    return eval_after - eval_before


def cheap_pass(
    moves: list[ParsedMove],
    book_exit_ply: int,
    *,
    threshold: int = CHEAP_DELTA_THRESHOLD,
    decided_cp: int = DECIDED_CP,
) -> tuple[list[Candidate], list[int]]:
    """Scan the user's post-book moves using Lichess evals.

    Returns ``(candidates, needs_engine_scan)`` where ``needs_engine_scan`` is the list of user
    plies that lacked the evals to score and must be checked by the 100k-node engine fallback.
    """
    candidates: list[Candidate] = []
    needs_scan: list[int] = []

    for m in moves:
        if not m.is_user_move or m.ply < book_exit_ply:
            continue

        eval_after = m.eval_cp
        eval_before = moves[m.ply - 1].eval_cp if m.ply > 0 else 0
        if eval_after is None or eval_before is None:
            needs_scan.append(m.ply)
            continue

        if abs(eval_before) > decided_cp:
            continue

        loss = loss_cp(eval_before, eval_after, m.color)
        if loss >= threshold:
            candidates.append(Candidate(ply=m.ply, loss_cp=loss, source="lichess_eval"))

    return candidates, needs_scan
