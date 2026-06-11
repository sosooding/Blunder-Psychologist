from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from blunder.queue import claim_one, enqueue, mark_done, mark_failed


def _status(session, job_id: int) -> str:
    return session.execute(
        text("SELECT status FROM jobs WHERE id = :id"), {"id": job_id}
    ).scalar_one()


def test_enqueue_and_claim(session):
    job_id = enqueue(session, "hello", {"name": "x"}, priority=5)

    claimed = claim_one(session)
    assert claimed is not None
    assert claimed.id == job_id
    assert claimed.type == "hello"
    assert claimed.payload == {"name": "x"}
    assert claimed.attempts == 1
    assert _status(session, job_id) == "running"


def test_claim_returns_none_when_empty(session):
    assert claim_one(session) is None


def test_priority_ordering(session):
    low = enqueue(session, "hello", {"n": 1}, priority=10)
    high = enqueue(session, "hello", {"n": 2}, priority=0)

    assert claim_one(session).id == high  # priority 0 drained first
    assert claim_one(session).id == low


def test_skip_locked(engine, session):
    first = enqueue(session, "hello", {"n": "a"}, priority=0)
    second = enqueue(session, "hello", {"n": "b"}, priority=0)

    # Hold a row lock on `first` in a separate, uncommitted transaction.
    OtherSession = sessionmaker(bind=engine, future=True)
    other = OtherSession()
    locked_id = other.execute(
        text(
            "SELECT id FROM jobs WHERE status = 'pending' "
            "ORDER BY priority, created_at FOR UPDATE SKIP LOCKED LIMIT 1"
        )
    ).scalar_one()
    assert locked_id == first

    # Our claim must skip the locked row and take `second` instead.
    claimed = claim_one(session)
    assert claimed is not None
    assert claimed.id == second

    other.rollback()
    other.close()


def test_failure_retries_then_dead(session):
    job_id = enqueue(session, "hello", {}, priority=0)

    claimed = claim_one(session)  # attempts -> 1
    mark_failed(session, claimed.id, claimed.attempts, "boom", max_attempts=3)
    assert _status(session, job_id) == "pending"  # retried

    claimed = claim_one(session)  # attempts -> 2
    mark_failed(session, claimed.id, claimed.attempts, "boom", max_attempts=3)
    assert _status(session, job_id) == "pending"

    claimed = claim_one(session)  # attempts -> 3
    mark_failed(session, claimed.id, claimed.attempts, "boom", max_attempts=3)
    assert _status(session, job_id) == "dead"  # dead-lettered at the cap


def test_mark_done(session):
    job_id = enqueue(session, "hello", {}, priority=0)
    claimed = claim_one(session)
    mark_done(session, claimed.id)
    assert _status(session, job_id) == "done"
