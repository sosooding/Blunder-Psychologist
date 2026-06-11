"""Job type registry. Handlers register via the @register decorator and are dispatched
by the worker on the job's ``type``."""

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("blunder.jobs")

JobHandler = Callable[[dict[str, Any]], None]
REGISTRY: dict[str, JobHandler] = {}


def register(job_type: str) -> Callable[[JobHandler], JobHandler]:
    def decorator(fn: JobHandler) -> JobHandler:
        REGISTRY[job_type] = fn
        return fn

    return decorator


@register("hello")
def handle_hello(payload: dict[str, Any]) -> None:
    name = payload.get("name", "world")
    logger.info("hello, %s  (the queue works)", name)
