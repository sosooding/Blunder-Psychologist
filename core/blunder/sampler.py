"""Backfill sampler: choose which of a user's games to analyse.

Pure over a list of game records (the NDJSON dicts from ``lichess.py``). Three strategies:

* ``recent``     — the newest ``cap`` games.
* ``random``     — a uniform random ``cap`` games.
* ``stratified`` — the default: the newest ``recent_n`` plus a random ``older_n`` from the rest,
  so the profile reflects both current form and longer-standing habits without analysing a whole
  history. Capped at ``cap`` (default 400).

Randomness takes an injected ``random.Random`` so sampling is reproducible in tests.
"""

import random
from typing import Any

Game = dict[str, Any]

DEFAULT_CAP = 400
DEFAULT_RECENT_N = 300
DEFAULT_OLDER_N = 100


def _newest_first(games: list[Game]) -> list[Game]:
    return sorted(games, key=lambda g: g.get("createdAt", 0), reverse=True)


def sample(
    games: list[Game],
    strategy: str = "stratified",
    *,
    cap: int = DEFAULT_CAP,
    recent_n: int = DEFAULT_RECENT_N,
    older_n: int = DEFAULT_OLDER_N,
    rng: random.Random | None = None,
) -> list[Game]:
    """Return the subset of ``games`` to backfill, newest first."""
    if strategy not in ("recent", "random", "stratified"):
        raise ValueError(f"unknown sampling strategy: {strategy!r}")

    rng = rng or random.Random()
    ordered = _newest_first(games)

    if len(ordered) <= cap:
        return ordered

    if strategy == "recent":
        return ordered[:cap]

    if strategy == "random":
        return _newest_first(rng.sample(ordered, cap))

    # stratified
    recent = ordered[:recent_n]
    older_pool = ordered[recent_n:]
    take = min(older_n, cap - len(recent), len(older_pool))
    older = rng.sample(older_pool, take) if take > 0 else []
    return _newest_first(recent + older)
