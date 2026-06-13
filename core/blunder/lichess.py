"""Lichess HTTP client: game export (NDJSON streaming) and the opening explorer.

Game export uses ``pgnInJson=true`` so each NDJSON record carries both structured metadata
(id, speed, players, timestamps) *and* the full PGN with ``[%eval]``/``[%clk]`` annotations —
the metadata is more reliable than parsing PGN headers, and python-chess reads the clocks and
embedded evals straight out of the PGN field downstream (see ``ingest.py``).

429s are retried with exponential backoff, honouring ``Retry-After`` when present. The transport
and the sleep function are injectable so the whole client is exercised against committed fixtures
with no network (see ``tests/test_lichess.py``).
"""

import json
import logging
import time
from collections.abc import Callable, Iterator
from typing import Any

import httpx

logger = logging.getLogger("blunder.lichess")

LICHESS_BASE = "https://lichess.org"
EXPLORER_BASE = "https://explorer.lichess.ovh"

# Backoff cap per retry, seconds. Lichess asks clients to wait ~60s after a 429; we cap there.
_MAX_BACKOFF = 60.0


class LichessError(RuntimeError):
    """Non-retryable error talking to Lichess (4xx other than 429, or retries exhausted)."""


class LichessClient:
    def __init__(
        self,
        token: str | None = None,
        *,
        base_url: str = LICHESS_BASE,
        explorer_base_url: str = EXPLORER_BASE,
        transport: httpx.BaseTransport | None = None,
        max_retries: int = 5,
        sleep: Callable[[float], None] = time.sleep,
        timeout: float = 30.0,
    ) -> None:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._games = httpx.Client(
            base_url=base_url, headers=headers, transport=transport, timeout=timeout
        )
        self._explorer = httpx.Client(
            base_url=explorer_base_url, transport=transport, timeout=timeout
        )
        self._max_retries = max_retries
        self._sleep = sleep

    def __enter__(self) -> "LichessClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._games.close()
        self._explorer.close()

    # -- game export -----------------------------------------------------------------

    def stream_user_games(
        self,
        username: str,
        *,
        max_games: int = 400,
        since_ms: int | None = None,
        perf_types: tuple[str, ...] = ("rapid", "classical"),
        rated: bool = True,
    ) -> Iterator[dict[str, Any]]:
        """Yield one parsed NDJSON game record per game, newest first.

        Bullet/blitz are excluded server-side via ``perfType``. ``since_ms`` (epoch ms) drives
        incremental sync — pass the user's ``last_synced_at`` to fetch only newer games.
        """
        params: dict[str, Any] = {
            "max": max_games,
            "rated": str(rated).lower(),
            "perfType": ",".join(perf_types),
            "clocks": "true",
            "evals": "true",
            "pgnInJson": "true",
            "sort": "dateDesc",
        }
        if since_ms is not None:
            params["since"] = since_ms

        path = f"/api/games/user/{username}"
        headers = {"Accept": "application/x-ndjson"}

        for attempt in range(1, self._max_retries + 1):
            with self._games.stream("GET", path, params=params, headers=headers) as resp:
                if resp.status_code == 429:
                    resp.read()  # drain so the connection can be reused
                    self._backoff(resp, attempt)
                    continue
                if resp.status_code >= 400:
                    resp.read()
                    raise LichessError(f"GET {path} -> {resp.status_code}: {resp.text[:200]}")
                for line in resp.iter_lines():
                    if line.strip():
                        yield json.loads(line)
                return
        raise LichessError(f"GET {path} -> 429 after {self._max_retries} attempts")

    def export_game(self, game_id: str) -> dict[str, Any]:
        """Fetch a single game as a JSON record (with PGN), for on-demand analysis by URL/id."""
        params = {"clocks": "true", "evals": "true", "pgnInJson": "true"}
        headers = {"Accept": "application/json"}
        for attempt in range(1, self._max_retries + 1):
            resp = self._games.get(f"/game/export/{game_id}", params=params, headers=headers)
            if resp.status_code == 429:
                self._backoff(resp, attempt)
                continue
            if resp.status_code >= 400:
                raise LichessError(f"export {game_id} -> {resp.status_code}: {resp.text[:200]}")
            return resp.json()
        raise LichessError(f"export {game_id} -> 429 after {self._max_retries} attempts")

    # -- opening explorer ------------------------------------------------------------

    def opening_explorer(self, fen: str) -> dict[str, Any]:
        """Aggregate stats for a position in the Lichess games database.

        Returns the raw response; ``white + draws + black`` is the games-count used for
        book-exit detection (see ``book.py``). We ask for no move/game detail to keep it small.
        """
        params = {"fen": fen, "moves": 0, "topGames": 0, "recentGames": 0}
        for attempt in range(1, self._max_retries + 1):
            resp = self._explorer.get("/lichess", params=params)
            if resp.status_code == 429:
                self._backoff(resp, attempt)
                continue
            if resp.status_code >= 400:
                raise LichessError(f"explorer {resp.status_code}: {resp.text[:200]}")
            return resp.json()
        raise LichessError(f"explorer -> 429 after {self._max_retries} attempts")

    # -- internals -------------------------------------------------------------------

    def _backoff(self, resp: httpx.Response, attempt: int) -> None:
        retry_after = resp.headers.get("Retry-After")
        if retry_after is not None:
            try:
                delay = float(retry_after)
            except ValueError:
                delay = _MAX_BACKOFF
        else:
            delay = min(_MAX_BACKOFF, 2.0**attempt)
        logger.warning("lichess 429 (attempt %d); backing off %.1fs", attempt, delay)
        self._sleep(delay)
