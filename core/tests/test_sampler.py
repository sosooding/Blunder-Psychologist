"""Sampler tests — pure, deterministic via an injected RNG."""

import random

from blunder.sampler import sample


def _games(n: int) -> list[dict]:
    # createdAt descending-friendly: game i is older as i grows. Shuffled order on input
    # to prove the sampler sorts internally.
    games = [{"id": f"g{i:04d}", "createdAt": 2_000_000 - i} for i in range(n)]
    random.Random(1).shuffle(games)
    return games


def test_returns_all_when_under_cap():
    games = _games(50)
    out = sample(games, "stratified", cap=400)
    assert len(out) == 50
    # newest first
    assert [g["createdAt"] for g in out] == sorted(
        (g["createdAt"] for g in games), reverse=True
    )


def test_recent_takes_newest_cap():
    games = _games(1000)
    out = sample(games, "recent", cap=400)
    assert len(out) == 400
    assert out[0]["id"] == "g0000"  # newest (largest createdAt)
    assert out[-1]["id"] == "g0399"
    assert all(out[i]["createdAt"] >= out[i + 1]["createdAt"] for i in range(len(out) - 1))


def test_random_is_capped_and_reproducible():
    games = _games(1000)
    a = sample(games, "random", cap=400, rng=random.Random(7))
    b = sample(games, "random", cap=400, rng=random.Random(7))
    c = sample(games, "random", cap=400, rng=random.Random(8))
    assert len(a) == 400
    assert [g["id"] for g in a] == [g["id"] for g in b]  # same seed -> identical
    assert [g["id"] for g in a] != [g["id"] for g in c]  # different seed -> different
    assert all(a[i]["createdAt"] >= a[i + 1]["createdAt"] for i in range(len(a) - 1))


def test_stratified_keeps_all_recent_and_samples_older():
    games = _games(1000)
    out = sample(games, "stratified", cap=400, recent_n=300, older_n=100, rng=random.Random(3))
    assert len(out) == 400

    ids = {g["id"] for g in out}
    # The 300 newest must all be present.
    assert {f"g{i:04d}" for i in range(300)}.issubset(ids)
    # The remaining 100 come from the older pool (ids g0300..g0999).
    older_selected = ids - {f"g{i:04d}" for i in range(300)}
    assert len(older_selected) == 100
    assert all(int(gid[1:]) >= 300 for gid in older_selected)
    assert all(out[i]["createdAt"] >= out[i + 1]["createdAt"] for i in range(len(out) - 1))


def test_stratified_reproducible_with_seed():
    games = _games(1000)
    a = sample(games, "stratified", cap=400, rng=random.Random(99))
    b = sample(games, "stratified", cap=400, rng=random.Random(99))
    assert [g["id"] for g in a] == [g["id"] for g in b]


def test_unknown_strategy_raises():
    import pytest

    with pytest.raises(ValueError, match="unknown sampling strategy"):
        sample(_games(10), "nonsense")
