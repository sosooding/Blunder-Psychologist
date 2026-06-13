"""Lichess client tests — driven entirely off committed fixtures via httpx.MockTransport.
No network is touched."""

from pathlib import Path

import httpx
import pytest

from blunder.lichess import LichessClient, LichessError

FIXTURES = Path(__file__).parent / "fixtures"


def _ndjson_bytes() -> bytes:
    return (FIXTURES / "user_games.ndjson").read_bytes()


def test_stream_user_games_yields_records_with_expected_query_and_headers():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = request.url
        captured["headers"] = request.headers
        return httpx.Response(200, content=_ndjson_bytes())

    client = LichessClient(token="tok", transport=httpx.MockTransport(handler))
    games = list(client.stream_user_games("alice", max_games=400, since_ms=123))

    assert [g["id"] for g in games] == ["g0000003", "g0000001", "g0000002"]
    assert games[1]["pgn"].lstrip().startswith("[Event")

    q = captured["url"].params
    assert q["clocks"] == "true"
    assert q["evals"] == "true"
    assert q["pgnInJson"] == "true"
    assert q["perfType"] == "rapid,classical"
    assert q["rated"] == "true"
    assert q["max"] == "400"
    assert q["since"] == "123"
    assert captured["headers"]["authorization"] == "Bearer tok"
    assert captured["headers"]["accept"] == "application/x-ndjson"
    client.close()


def test_no_token_means_no_auth_header_and_no_since_param():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = request.url
        captured["headers"] = request.headers
        return httpx.Response(200, content=_ndjson_bytes())

    client = LichessClient(transport=httpx.MockTransport(handler))
    list(client.stream_user_games("alice"))

    assert "authorization" not in captured["headers"]
    assert "since" not in captured["url"].params
    client.close()


def test_stream_retries_on_429_then_succeeds_honouring_retry_after():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0.01"}, content=b"slow down")
        return httpx.Response(200, content=_ndjson_bytes())

    slept: list[float] = []
    client = LichessClient(transport=httpx.MockTransport(handler), sleep=slept.append)
    games = list(client.stream_user_games("alice"))

    assert calls["n"] == 2
    assert slept == [0.01]
    assert len(games) == 3
    client.close()


def test_stream_raises_after_retries_exhausted():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, content=b"nope")

    client = LichessClient(
        transport=httpx.MockTransport(handler), sleep=lambda _d: None, max_retries=3
    )
    with pytest.raises(LichessError, match="429 after 3 attempts"):
        list(client.stream_user_games("alice"))
    client.close()


def test_stream_raises_on_other_4xx():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"no such user")

    client = LichessClient(transport=httpx.MockTransport(handler))
    with pytest.raises(LichessError, match="404"):
        list(client.stream_user_games("ghost"))
    client.close()


def test_opening_explorer_parses_and_hits_explorer_host():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = request.url
        return httpx.Response(200, json={"white": 100, "draws": 50, "black": 80, "moves": []})

    client = LichessClient(transport=httpx.MockTransport(handler))
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    data = client.opening_explorer(fen)

    assert data["white"] == 100
    assert "explorer.lichess.ovh" in str(captured["url"])
    assert captured["url"].params["fen"].startswith("rnbqkbnr")
    client.close()


def test_explorer_carries_token_and_user_agent():
    # The opening explorer rejects anonymous requests (401), so the token must reach it too.
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        return httpx.Response(200, json={"white": 1, "draws": 0, "black": 0, "moves": []})

    client = LichessClient(token="tok", transport=httpx.MockTransport(handler))
    client.opening_explorer("8/8/8/8/8/8/4k3/4K3 w - - 0 1")

    assert captured["headers"]["authorization"] == "Bearer tok"
    assert captured["headers"]["user-agent"] == "blunder-psychologist"
    client.close()
