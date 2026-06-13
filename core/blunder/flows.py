"""Funnel orchestration: backfill → scan_chunk → deep_analyze, plus on-demand analyze_game.

These functions take every collaborator (DB session, Lichess client, engine analyzer, enqueue
callable) as an argument, so the whole funnel is driven end-to-end in tests against a real
Postgres with a fake transport and a fake analyzer — no network, no Stockfish. The job handlers
in ``handlers.py`` are the thin wiring that builds the real collaborators from settings.
"""

import logging
import re
from collections.abc import Callable
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from . import ingest
from .book import CachedExplorer, detect_book_exit
from .deep import deep_analyze, scan_user_moves
from .engine import DEEP_NODES, Analyzer
from .funnel import cheap_pass
from .lichess import LichessClient

logger = logging.getLogger("blunder.flows")

# enqueue(type, payload, priority) -> job id
Enqueue = Callable[[str, dict[str, Any], int], int]

PRIORITY_ONDEMAND = 0
PRIORITY_BACKFILL = 10

_GAME_URL_ID = re.compile(r"lichess\.org/(\w{8})")


def game_id_from_url(url: str) -> str:
    m = _GAME_URL_ID.search(url)
    if not m:
        raise ValueError(f"not a Lichess game URL: {url!r}")
    return m.group(1)


def run_backfill(
    session: Session,
    client: LichessClient,
    username: str,
    *,
    strategy: str,
    max_games: int,
    since_ms: int | None,
    chunk_size: int,
    enqueue: Enqueue,
) -> dict[str, int]:
    """Fetch + sample a user's games, persist them, fan out scan_chunk jobs over the new ones."""
    from .sampler import sample  # local import keeps the module's import graph shallow

    fetched = list(client.stream_user_games(username, max_games=max_games, since_ms=since_ms))
    sampled = sample(fetched, strategy, cap=max_games)

    user_id = ingest.upsert_user(session, username)
    new_ids: list[int] = []
    for record in sampled:
        pg = ingest.parse_game(record, username)
        game_id, created = ingest.upsert_game(session, user_id, pg)
        if created:
            new_ids.append(game_id)

    session.execute(
        text("UPDATE users SET last_synced_at = now() WHERE id = :id"), {"id": user_id}
    )
    session.commit()

    chunks = [new_ids[i : i + chunk_size] for i in range(0, len(new_ids), chunk_size)]
    for chunk in chunks:
        enqueue("scan_chunk", {"username": username, "game_ids": chunk}, PRIORITY_BACKFILL)

    logger.info(
        "backfill %s: fetched=%d sampled=%d new=%d chunks=%d",
        username, len(fetched), len(sampled), len(new_ids), len(chunks),
    )
    return {
        "fetched": len(fetched),
        "sampled": len(sampled),
        "new": len(new_ids),
        "chunks": len(chunks),
    }


def _load_pgn(session: Session, game_id: int) -> str | None:
    return session.execute(
        text("SELECT pgn FROM games WHERE id = :id"), {"id": game_id}
    ).scalar_one_or_none()


def _find_candidates(
    session: Session,
    client: LichessClient,
    analyzer: Analyzer,
    pg: ingest.ParsedGame,
    *,
    book_threshold: int,
    cheap_threshold: int,
    scan_nodes: int,
) -> tuple[int, list[int]]:
    """Book-exit detect, cheap pass, and engine-scan fallback. Returns (book_exit_ply, plies)."""
    explorer = CachedExplorer(session, client)
    fens_before = [m.fen_before for m in pg.moves]
    book_exit_ply = detect_book_exit(fens_before, explorer, threshold=book_threshold)

    candidates, needs_scan = cheap_pass(pg.moves, book_exit_ply, threshold=cheap_threshold)
    candidates += scan_user_moves(
        pg, needs_scan, analyzer, nodes=scan_nodes, threshold=cheap_threshold
    )
    return book_exit_ply, sorted({c.ply for c in candidates})


def run_scan_chunk(
    session: Session,
    client: LichessClient,
    analyzer: Analyzer,
    username: str,
    game_ids: list[int],
    *,
    book_threshold: int,
    cheap_threshold: int,
    scan_nodes: int,
    enqueue: Enqueue,
) -> dict[str, int]:
    """Cheap pass over a chunk of games; enqueue deep_analyze for those with candidates.

    Logs the funnel ratio (candidate plies / total plies) — the measured number for the README.
    """
    total_plies = 0
    total_candidates = 0
    deep_jobs = 0

    for game_id in game_ids:
        pgn = _load_pgn(session, game_id)
        if pgn is None:
            logger.warning("scan_chunk: game id=%s vanished; skipping", game_id)
            continue
        pg = ingest.parse_pgn(pgn, username)
        book_exit_ply, plies = _find_candidates(
            session, client, analyzer, pg,
            book_threshold=book_threshold, cheap_threshold=cheap_threshold, scan_nodes=scan_nodes,
        )
        session.execute(
            text("UPDATE games SET book_exit_ply = :b WHERE id = :id"),
            {"b": book_exit_ply, "id": game_id},
        )
        total_plies += len(pg.moves)

        if plies:
            total_candidates += len(plies)
            enqueue(
                "deep_analyze",
                {"username": username, "game_id": game_id, "candidate_plies": plies},
                PRIORITY_BACKFILL,
            )
            deep_jobs += 1
        else:
            # No candidates — nothing to deep-analyze; the game is fully handled.
            session.execute(
                text("UPDATE games SET analysis_status = 'analyzed' WHERE id = :id"),
                {"id": game_id},
            )
    session.commit()

    ratio = (total_plies / total_candidates) if total_candidates else float("inf")
    logger.info(
        "scan_chunk %s: games=%d total_plies=%d candidates=%d deep_jobs=%d funnel_ratio=%.1fx",
        username, len(game_ids), total_plies, total_candidates, deep_jobs, ratio,
    )
    return {
        "games": len(game_ids),
        "total_plies": total_plies,
        "candidates": total_candidates,
        "deep_jobs": deep_jobs,
    }


def run_deep_analyze(
    session: Session,
    analyzer: Analyzer,
    username: str,
    game_id: int,
    candidate_plies: list[int],
    *,
    nodes: int = DEEP_NODES,
) -> dict[str, int]:
    """Deep-analyse a game's candidate plies and persist move_analyses + blunders."""
    pgn = _load_pgn(session, game_id)
    if pgn is None:
        logger.warning("deep_analyze: game id=%s vanished; skipping", game_id)
        return {"analysed": 0, "flagged": 0}
    pg = ingest.parse_pgn(pgn, username)
    analysed, flagged = deep_analyze(session, game_id, pg, candidate_plies, analyzer, nodes=nodes)
    logger.info(
        "deep_analyze %s game=%d: analysed=%d flagged=%d", username, game_id, analysed, flagged
    )
    return {"analysed": analysed, "flagged": flagged}


def run_analyze_game(
    session: Session,
    client: LichessClient,
    analyzer: Analyzer,
    username: str,
    *,
    pgn: str | None = None,
    game_url: str | None = None,
    book_threshold: int,
    cheap_threshold: int,
    scan_nodes: int,
    deep_nodes: int = DEEP_NODES,
) -> dict[str, Any]:
    """On-demand single-game analysis (priority 0). Runs scan + deep inline for a fast result."""
    if pgn is not None:
        pg = ingest.parse_pgn(pgn, username)
    elif game_url is not None:
        record = client.export_game(game_id_from_url(game_url))
        pg = ingest.parse_game(record, username)
    else:
        raise ValueError("analyze_game needs either pgn or game_url")

    user_id = ingest.upsert_user(session, username)
    game_id, _created = ingest.upsert_game(session, user_id, pg)

    book_exit_ply, plies = _find_candidates(
        session, client, analyzer, pg,
        book_threshold=book_threshold, cheap_threshold=cheap_threshold, scan_nodes=scan_nodes,
    )
    session.execute(
        text("UPDATE games SET book_exit_ply = :b WHERE id = :id"),
        {"b": book_exit_ply, "id": game_id},
    )
    session.commit()

    result = run_deep_analyze(session, analyzer, username, game_id, plies, nodes=deep_nodes)
    return {"game_id": game_id, "candidates": len(plies), **result}
