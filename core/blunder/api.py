from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from .db import SessionLocal
from .flows import PRIORITY_BACKFILL, PRIORITY_ONDEMAND
from .queue import enqueue

app = FastAPI(title="Blunder Psychologist API", version="0.0.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


class HelloRequest(BaseModel):
    name: str = "world"


@app.post("/jobs/hello")
def enqueue_hello(req: HelloRequest) -> dict[str, object]:
    with SessionLocal() as session:
        job_id = enqueue(session, "hello", {"name": req.name}, priority=PRIORITY_ONDEMAND)
    return {"job_id": job_id, "status": "queued"}


class BackfillRequest(BaseModel):
    strategy: str | None = None
    max_games: int | None = None
    full: bool = False  # ignore last_synced_at and re-fetch the whole window


@app.post("/users/{username}/backfill")
def backfill(username: str, req: BackfillRequest) -> dict[str, object]:
    """Enqueue a backfill (priority 10). Incremental by default: only games newer than the user's
    last sync are fetched; pass ``full=true`` to re-fetch the whole window."""
    with SessionLocal() as session:
        since_ms: int | None = None
        if not req.full:
            last = session.execute(
                text("SELECT last_synced_at FROM users WHERE lichess_username = :u"),
                {"u": username},
            ).scalar_one_or_none()
            if last is not None:
                since_ms = int(last.timestamp() * 1000)

        payload: dict[str, object] = {"username": username, "since_ms": since_ms}
        if req.strategy:
            payload["strategy"] = req.strategy
        if req.max_games:
            payload["max_games"] = req.max_games
        job_id = enqueue(session, "backfill", payload, priority=PRIORITY_BACKFILL)
    return {"job_id": job_id, "status": "queued", "since_ms": since_ms}


class AnalyzeGameRequest(BaseModel):
    username: str
    pgn: str | None = None
    game_url: str | None = None


@app.post("/games/analyze")
def analyze_game(req: AnalyzeGameRequest) -> dict[str, object]:
    """Enqueue an on-demand single-game analysis at priority 0 — it jumps the backfill queue."""
    if not req.pgn and not req.game_url:
        raise HTTPException(status_code=422, detail="provide either pgn or game_url")
    with SessionLocal() as session:
        job_id = enqueue(
            session,
            "analyze_game",
            {"username": req.username, "pgn": req.pgn, "game_url": req.game_url},
            priority=PRIORITY_ONDEMAND,
        )
    return {"job_id": job_id, "status": "queued"}


@app.get("/users/{username}/status")
def user_status(username: str) -> dict[str, object]:
    with SessionLocal() as session:
        user = session.execute(
            text("SELECT id, last_synced_at FROM users WHERE lichess_username = :u"),
            {"u": username},
        ).fetchone()
        if user is None:
            raise HTTPException(status_code=404, detail="unknown user")
        user_id, last_synced_at = user

        games_total = session.execute(
            text("SELECT count(*) FROM games WHERE user_id = :id"), {"id": user_id}
        ).scalar_one()
        games_analyzed = session.execute(
            text(
                "SELECT count(*) FROM games WHERE user_id = :id AND analysis_status = 'analyzed'"
            ),
            {"id": user_id},
        ).scalar_one()
        blunders = session.execute(
            text(
                "SELECT count(*) FROM blunders b "
                "JOIN move_analyses m ON m.id = b.move_analysis_id "
                "JOIN games g ON g.id = m.game_id WHERE g.user_id = :id"
            ),
            {"id": user_id},
        ).scalar_one()
        pending_jobs = session.execute(
            text(
                "SELECT count(*) FROM jobs WHERE status IN ('pending', 'running') "
                "AND payload->>'username' = :u"
            ),
            {"u": username},
        ).scalar_one()

    return {
        "username": username,
        "last_synced_at": last_synced_at.isoformat() if last_synced_at else None,
        "games_total": games_total,
        "games_analyzed": games_analyzed,
        "blunders": blunders,
        "pending_jobs": pending_jobs,
    }
