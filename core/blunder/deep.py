"""Deep pass: analyse candidate plies at full depth and persist move_analyses + blunders.

Also hosts the cheap pass's engine fallback (``scan_user_moves``) — the 100k-node triage for user
moves that had no Lichess eval. Both take an injected ``Analyzer`` so the write logic is tested
with a fake engine and a real DB; the native wheel only runs in the worker image.

Only user-side candidate moves are stored as move_analyses / blunders. Opponent positions are
evaluated solely as delta inputs inside the engine and never persisted.
"""

import json
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from .engine import DEEP_NODES, SCAN_NODES, Analyzer, DeepResult, classify_phase, is_flagged
from .funnel import CHEAP_DELTA_THRESHOLD, Candidate
from .ingest import ParsedGame

logger = logging.getLogger("blunder.deep")


def _positions(pg: ParsedGame, plies: list[int]) -> list[tuple[str, str]]:
    return [(pg.moves[p].fen_before, pg.moves[p].uci) for p in plies]


def scan_user_moves(
    pg: ParsedGame,
    plies: list[int],
    analyzer: Analyzer,
    *,
    nodes: int = SCAN_NODES,
    threshold: int = CHEAP_DELTA_THRESHOLD,
) -> list[Candidate]:
    """Engine fallback for the cheap pass: scan the given user plies at low node count and flag
    those whose mover-loss clears ``threshold``."""
    if not plies:
        return []
    results = analyzer.analyze(_positions(pg, plies), nodes=nodes)
    candidates: list[Candidate] = []
    for ply, r in zip(plies, results, strict=True):
        if r is not None and r.delta_cp >= threshold:
            candidates.append(Candidate(ply=ply, loss_cp=r.delta_cp, source="engine_scan"))
    return candidates


def move_analysis_params(game_id: int, pg: ParsedGame, ply: int, r: DeepResult) -> dict:
    """Build the move_analyses row values from a deep result (pure; no DB)."""
    m = pg.moves[ply]
    return {
        "gid": game_id,
        "ply": ply,
        "fen": m.fen_before,
        "move": m.san,
        "eval_cp": r.eval_cp,
        "best_eval_cp": r.best_eval_cp,
        "delta_cp": r.delta_cp,
        "sharpness": float(r.sharpness),
        "clock": m.clock_seconds,
        "phase": classify_phase(m.fen_before),
        "arch": r.archetype,
        "features": json.dumps(r.features),
        "best_pv": json.dumps(r.best_pv),
    }


_UPSERT_MOVE = text(
    """
    INSERT INTO move_analyses
        (game_id, ply, fen, move, eval_cp, best_eval_cp, delta_cp, sharpness,
         clock_seconds, phase, pawn_archetype, features, best_pv)
    VALUES
        (:gid, :ply, :fen, :move, :eval_cp, :best_eval_cp, :delta_cp, :sharpness,
         :clock, :phase, :arch, cast(:features as jsonb), cast(:best_pv as jsonb))
    ON CONFLICT (game_id, ply) DO UPDATE SET
        fen = EXCLUDED.fen, move = EXCLUDED.move, eval_cp = EXCLUDED.eval_cp,
        best_eval_cp = EXCLUDED.best_eval_cp, delta_cp = EXCLUDED.delta_cp,
        sharpness = EXCLUDED.sharpness, clock_seconds = EXCLUDED.clock_seconds,
        phase = EXCLUDED.phase, pawn_archetype = EXCLUDED.pawn_archetype,
        features = EXCLUDED.features, best_pv = EXCLUDED.best_pv
    RETURNING id
    """
)


def deep_analyze(
    session: Session,
    game_id: int,
    pg: ParsedGame,
    candidate_plies: list[int],
    analyzer: Analyzer,
    *,
    nodes: int = DEEP_NODES,
    multipv: int = 3,
) -> tuple[int, int]:
    """Deep-analyse the candidate plies and persist rows. Returns (analysed, flagged).

    Idempotent: re-analysing a game upserts move_analyses by (game_id, ply) and refreshes the
    blunder row for each, so re-runs don't duplicate.
    """
    plies = sorted(set(candidate_plies))
    results = analyzer.analyze(_positions(pg, plies), nodes=nodes, multipv=multipv)

    analysed = 0
    flagged = 0
    for ply, r in zip(plies, results, strict=True):
        if r is None:
            continue
        params = move_analysis_params(game_id, pg, ply, r)
        ma_id = session.execute(_UPSERT_MOVE, params).scalar_one()
        session.execute(
            text("DELETE FROM blunders WHERE move_analysis_id = :id"), {"id": ma_id}
        )
        if is_flagged(r):
            session.execute(
                text("INSERT INTO blunders (move_analysis_id, severity) VALUES (:id, :sev)"),
                {"id": ma_id, "sev": r.severity},
            )
            flagged += 1
        analysed += 1

    session.execute(
        text("UPDATE games SET analysis_status = 'analyzed' WHERE id = :id"), {"id": game_id}
    )
    session.commit()
    return analysed, flagged
