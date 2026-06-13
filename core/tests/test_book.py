"""Book-exit detection tests — pure, with a fake explorer (no DB, no network)."""

from blunder.book import detect_book_exit


def _explorer(counts: dict[str, int | None]):
    """Build an explorer from fen->count; a None value simulates the explorer being unavailable."""
    calls: list[str] = []

    def explorer(fen: str) -> int | None:
        calls.append(fen)
        return counts.get(fen, 0)  # unknown position -> 0 games (out of book)

    explorer.calls = calls  # type: ignore[attr-defined]
    return explorer


def test_exit_at_first_position_below_threshold():
    fens = ["p0", "p1", "p2", "p3", "p4"]
    counts = {"p0": 50000, "p1": 8000, "p2": 300, "p3": 40, "p4": 5}
    explorer = _explorer(counts)
    # p3 is the first under threshold=100 -> ply 3.
    assert detect_book_exit(fens, explorer, threshold=100) == 3


def test_stops_querying_once_exit_found():
    fens = ["p0", "p1", "p2", "p3", "p4"]
    counts = {"p0": 50000, "p1": 40, "p2": 999, "p3": 999, "p4": 999}
    explorer = _explorer(counts)
    assert detect_book_exit(fens, explorer, threshold=100) == 1
    # Only p0 and p1 should have been queried.
    assert explorer.calls == ["p0", "p1"]


def test_whole_game_in_book_returns_len():
    fens = ["p0", "p1", "p2"]
    counts = {"p0": 50000, "p1": 8000, "p2": 5000}
    assert detect_book_exit(fens, _explorer(counts), threshold=100) == 3


def test_unavailable_explorer_falls_back_to_flat_ply():
    fens = [f"p{i}" for i in range(30)]
    counts = {"p0": 50000, "p1": None}  # explorer goes down at p1
    assert detect_book_exit(fens, _explorer(counts), threshold=100, fallback_ply=20) == 20


def test_fallback_is_clamped_to_game_length():
    fens = ["p0", "p1", "p2"]  # short game
    counts = {"p0": None}
    assert detect_book_exit(fens, _explorer(counts), fallback_ply=20) == 3


def test_zero_count_unknown_position_is_out_of_book():
    fens = ["p0", "p1", "p2"]
    counts = {"p0": 50000, "p1": 8000}  # p2 absent -> 0
    assert detect_book_exit(fens, _explorer(counts), threshold=100) == 2
