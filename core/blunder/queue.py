"""Postgres-backed priority job queue.

Workers claim the highest-priority (lowest number), oldest pending job atomically with
``SELECT … FOR UPDATE SKIP LOCKED``, so multiple workers never grab the same row and a
locked row never blocks another worker. No Redis, no Celery — deliberately.
"""

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass
class ClaimedJob:
    id: int
    type: str
    payload: dict[str, Any]
    attempts: int


def enqueue(
    session: Session,
    type: str,
    payload: dict[str, Any] | None = None,
    priority: int = 10,
) -> int:
    """Insert a pending job and return its id. Lower priority = drained first."""
    row = session.execute(
        text(
            "INSERT INTO jobs (type, priority, status, payload) "
            "VALUES (:type, :priority, 'pending', cast(:payload as jsonb)) "
            "RETURNING id"
        ),
        {"type": type, "priority": priority, "payload": json.dumps(payload or {})},
    ).one()
    session.commit()
    return int(row[0])


_CLAIM_SQL = text(
    """
    UPDATE jobs
    SET status = 'running', attempts = attempts + 1, updated_at = now()
    WHERE id = (
        SELECT id FROM jobs
        WHERE status = 'pending'
        ORDER BY priority ASC, created_at ASC
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING id, type, payload, attempts
    """
)


def claim_one(session: Session) -> ClaimedJob | None:
    """Atomically claim and return the next pending job, or None if the queue is empty."""
    row = session.execute(_CLAIM_SQL).fetchone()
    session.commit()
    if row is None:
        return None
    return ClaimedJob(id=row[0], type=row[1], payload=row[2] or {}, attempts=row[3])


def mark_done(session: Session, job_id: int) -> None:
    session.execute(
        text("UPDATE jobs SET status = 'done', updated_at = now() WHERE id = :id"),
        {"id": job_id},
    )
    session.commit()


def mark_failed(
    session: Session,
    job_id: int,
    attempts: int,
    error: str,
    max_attempts: int,
) -> None:
    """Retry (back to 'pending') until attempts hit the cap, then dead-letter ('dead')."""
    status = "dead" if attempts >= max_attempts else "pending"
    session.execute(
        text(
            "UPDATE jobs SET status = :status, last_error = :err, updated_at = now() "
            "WHERE id = :id"
        ),
        {"status": status, "err": error[:2000], "id": job_id},
    )
    session.commit()
