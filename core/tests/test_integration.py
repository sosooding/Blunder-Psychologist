"""End-to-end funnel test against a real Postgres.

Drives backfill → scan_chunk → deep_analyze through the actual job queue, with the Lichess client
backed by the committed NDJSON fixture (httpx MockTransport) and the engine replaced by a fake
analyzer. No network, no Stockfish — but real SQL, real dedup, real fan-out. Skips when no DB is
configured (see conftest)."""

import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text

from blunder import flows, queue
from blunder.engine import DeepResult
from blunder.lichess import LichessClient

FIXTURES = Path(__file__).parent / "fixtures"
_TABLES = "move_analyses, blunders, games, users, opening_cache, jobs"


def _ndjson_bytes() -> bytes:
    return (FIXTURES / "user_games.ndjson").read_bytes()


def _transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "explorer.lichess.ovh" in url:
            # 0 games for every position -> book exits at ply 0 (whole game is post-book).
            return httpx.Response(200, json={"white": 0, "draws": 0, "black": 0, "moves": []})
        if "/api/games/user/" in url:
            return httpx.Response(200, content=_ndjson_bytes())
        if "/game/export/" in url:
            # On-demand single game: return g1 as a JSON record.
            for line in _ndjson_bytes().splitlines():
                r = json.loads(line)
                if r["id"] == "g0000001":
                    return httpx.Response(200, json=r)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


class FakeBlunderAnalyzer:
    """Pretends every analysed position is a blunder, so the deep pass writes rows predictably."""

    def __init__(self):
        self.seen: list[tuple[str, str]] = []

    def analyze(self, positions, *, nodes, multipv=3):
        out = []
        for fen, uci in positions:
            self.seen.append((fen, uci))
            out.append(
                DeepResult(
                    fen=fen, move_uci=uci, move_san="?", white_to_move=True,
                    eval_cp=-250, best_eval_cp=50, delta_cp=300, sharpness=10,
                    severity="blunder", archetype="unknown", features={"space": 1},
                    best_pv=["a1a2"],
                )
            )
        return out


@pytest.fixture
def clean_db(engine):
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {_TABLES} RESTART IDENTITY CASCADE"))
    return engine


def _drain(session, client, analyzer) -> dict[str, int]:
    """Run the worker's dispatch loop in-process with injected fakes until the queue empties."""

    def enq(job_type, payload, priority=10):
        return queue.enqueue(session, job_type, payload, priority)

    counts: dict[str, int] = {}
    while (job := queue.claim_one(session)) is not None:
        counts[job.type] = counts.get(job.type, 0) + 1
        p = job.payload
        if job.type == "backfill":
            flows.run_backfill(
                session, client, p["username"], strategy="recent", max_games=400,
                since_ms=p.get("since_ms"), chunk_size=25, enqueue=enq,
            )
        elif job.type == "scan_chunk":
            flows.run_scan_chunk(
                session, client, analyzer, p["username"], p["game_ids"],
                book_threshold=100, cheap_threshold=100, scan_nodes=100_000, enqueue=enq,
            )
        elif job.type == "deep_analyze":
            flows.run_deep_analyze(
                session, analyzer, p["username"], p["game_id"], p["candidate_plies"], nodes=10
            )
        queue.mark_done(session, job.id)
    return counts


def test_backfill_funnel_end_to_end(clean_db, session):
    client = LichessClient(transport=_transport())
    analyzer = FakeBlunderAnalyzer()

    queue.enqueue(session, "backfill", {"username": "alice"}, 10)
    counts = _drain(session, client, analyzer)

    # backfill -> 1 scan_chunk (3 games < chunk size) -> 1 deep_analyze (only g2 has a candidate).
    assert counts == {"backfill": 1, "scan_chunk": 1, "deep_analyze": 1}

    games = session.execute(
        text("SELECT lichess_id, analysis_status, book_exit_ply FROM games ORDER BY lichess_id")
    ).all()
    assert [g[0] for g in games] == ["g0000001", "g0000002", "g0000003"]
    assert all(g[1] == "analyzed" for g in games)  # every scanned game ends analyzed
    assert all(g[2] == 0 for g in games)  # explorer said 0 games -> book exit at ply 0

    # The funnel's whole point: only candidate positions are deep-analysed, not every ply.
    ma = session.execute(
        text("SELECT game_id, ply, move, delta_cp, pawn_archetype FROM move_analyses")
    ).all()
    assert len(ma) == 1
    assert ma[0].move == "Ne4" and ma[0].ply == 9 and ma[0].delta_cp == 300

    blunders = session.execute(text("SELECT severity FROM blunders")).all()
    assert [b[0] for b in blunders] == ["blunder"]

    # The explorer lookups were cached.
    assert session.execute(text("SELECT count(*) FROM opening_cache")).scalar_one() >= 1

    # Downstream jobs ran at the backfill priority lane.
    prios = session.execute(
        text("SELECT DISTINCT priority FROM jobs WHERE type IN ('scan_chunk','deep_analyze')")
    ).scalars().all()
    assert prios == [10]

    client.close()


def test_backfill_is_idempotent(clean_db, session):
    client = LichessClient(transport=_transport())
    analyzer = FakeBlunderAnalyzer()

    queue.enqueue(session, "backfill", {"username": "alice"}, 10)
    _drain(session, client, analyzer)
    ma_first = session.execute(text("SELECT count(*) FROM move_analyses")).scalar_one()

    # Re-run: dedup on lichess_id means no new games, no new scan chunks, no duplicate rows.
    summary_holder = {}

    def enq(t, payload, pri=10):
        return queue.enqueue(session, t, payload, pri)

    summary_holder = flows.run_backfill(
        session, client, "alice", strategy="recent", max_games=400,
        since_ms=None, chunk_size=25, enqueue=enq,
    )
    assert summary_holder["new"] == 0
    assert summary_holder["chunks"] == 0

    _drain(session, client, analyzer)
    assert session.execute(text("SELECT count(*) FROM move_analyses")).scalar_one() == ma_first
    assert session.execute(text("SELECT count(*) FROM blunders")).scalar_one() == 1
    client.close()


def test_on_demand_analyze_game_by_pgn(clean_db, session):
    client = LichessClient(transport=_transport())
    analyzer = FakeBlunderAnalyzer()

    pgn = next(
        json.loads(line)["pgn"]
        for line in _ndjson_bytes().splitlines()
        if json.loads(line)["id"] == "g0000001"
    )
    # Analyse from Black's seat: ...b5 (ply 11) is Black's flagged move in this fixture.
    result = flows.run_analyze_game(
        session, client, analyzer, "bob", pgn=pgn,
        book_threshold=100, cheap_threshold=100, scan_nodes=100_000, deep_nodes=10,
    )
    assert result["candidates"] == 1
    assert result["flagged"] == 1

    row = session.execute(
        text("SELECT m.move, b.severity FROM blunders b JOIN move_analyses m "
             "ON m.id = b.move_analysis_id")
    ).one()
    assert row.move == "b5" and row.severity == "blunder"
    client.close()
