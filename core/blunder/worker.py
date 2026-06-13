"""Worker poll loop: claim a job, dispatch to its handler, mark done or retry/dead."""

import logging
import signal
import time
from types import FrameType

from . import handlers  # noqa: F401  (import registers the Phase 3 job handlers)
from .config import settings
from .db import SessionLocal
from .jobs import REGISTRY
from .queue import claim_one, mark_done, mark_failed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
logger = logging.getLogger("blunder.worker")

_shutdown = False


def _handle_signal(signum: int, _frame: FrameType | None) -> None:
    global _shutdown
    logger.info("received signal %s; finishing current job then exiting", signum)
    _shutdown = True


def run() -> None:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    logger.info("worker started; polling every %.1fs", settings.worker_poll_interval)

    while not _shutdown:
        with SessionLocal() as session:
            job = claim_one(session)

        if job is None:
            time.sleep(settings.worker_poll_interval)
            continue

        handler = REGISTRY.get(job.type)
        if handler is None:
            logger.error("no handler for job type %r (id=%s); dead-lettering", job.type, job.id)
            with SessionLocal() as session:
                mark_failed(
                    session,
                    job.id,
                    settings.worker_max_attempts,
                    f"no handler registered for type {job.type!r}",
                    settings.worker_max_attempts,
                )
            continue

        logger.info("claimed job id=%s type=%s attempt=%s", job.id, job.type, job.attempts)
        try:
            handler(job.payload)
        except Exception as exc:
            logger.exception("job id=%s failed", job.id)
            with SessionLocal() as session:
                mark_failed(session, job.id, job.attempts, str(exc), settings.worker_max_attempts)
        else:
            with SessionLocal() as session:
                mark_done(session, job.id)
            logger.info("job id=%s done", job.id)

    logger.info("worker stopped")


if __name__ == "__main__":
    run()
