"""Phase 3 job handlers. Importing this module registers the funnel job types on the worker.

Each handler builds the real collaborators (Lichess client, engine analyzer) from settings and
delegates to ``flows`` — all the logic and its tests live there with injected fakes.
"""

import logging
from collections.abc import Callable
from typing import Any

from . import flows, queue
from .config import settings
from .db import SessionLocal
from .engine import EngineAnalyzer
from .jobs import register
from .lichess import LichessClient

logger = logging.getLogger("blunder.handlers")


def _client() -> LichessClient:
    return LichessClient(token=settings.lichess_token)


def _analyzer() -> EngineAnalyzer:
    return EngineAnalyzer(stockfish_path=settings.stockfish_path, engines=settings.engine_count)


def _enqueuer(session) -> Callable[[str, dict[str, Any], int], int]:
    def _enq(job_type: str, payload: dict[str, Any], priority: int = 10) -> int:
        return queue.enqueue(session, job_type, payload, priority)

    return _enq


@register("backfill")
def handle_backfill(payload: dict[str, Any]) -> None:
    username = payload["username"]
    with SessionLocal() as session:
        client = _client()
        try:
            flows.run_backfill(
                session,
                client,
                username,
                strategy=payload.get("strategy", settings.backfill_strategy),
                max_games=payload.get("max_games", settings.backfill_max_games),
                since_ms=payload.get("since_ms"),
                chunk_size=settings.scan_chunk_size,
                enqueue=_enqueuer(session),
            )
        finally:
            client.close()


@register("scan_chunk")
def handle_scan_chunk(payload: dict[str, Any]) -> None:
    with SessionLocal() as session:
        client = _client()
        try:
            flows.run_scan_chunk(
                session,
                client,
                _analyzer(),
                payload["username"],
                payload["game_ids"],
                book_threshold=settings.book_threshold,
                cheap_threshold=settings.cheap_delta_threshold,
                scan_nodes=settings.scan_nodes,
                enqueue=_enqueuer(session),
            )
        finally:
            client.close()


@register("deep_analyze")
def handle_deep_analyze(payload: dict[str, Any]) -> None:
    with SessionLocal() as session:
        flows.run_deep_analyze(
            session,
            _analyzer(),
            payload["username"],
            payload["game_id"],
            payload["candidate_plies"],
            nodes=settings.deep_nodes,
        )


@register("analyze_game")
def handle_analyze_game(payload: dict[str, Any]) -> None:
    with SessionLocal() as session:
        client = _client()
        try:
            flows.run_analyze_game(
                session,
                client,
                _analyzer(),
                payload["username"],
                pgn=payload.get("pgn"),
                game_url=payload.get("game_url"),
                book_threshold=settings.book_threshold,
                cheap_threshold=settings.cheap_delta_threshold,
                scan_nodes=settings.scan_nodes,
                deep_nodes=settings.deep_nodes,
            )
        finally:
            client.close()
