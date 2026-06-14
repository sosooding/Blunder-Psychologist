"""Feature-diff tests — pure, driven by a fake extractor (no wheel, no engine, no DB)."""

import chess

from blunder.featurediff import NUMERIC_FIELDS, feature_diff, push_uci

# Black to move after 1.e4 e5 2.Nf3 — the g8 knight can go to f6 or e7.
FEN_BLACK_TO_MOVE = "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2"


def _feat(**over) -> dict:
    f = {k: 0 for k in NUMERIC_FIELDS}
    f["archetype"] = "unknown"
    f.update(over)
    return f


class FakeExtractor:
    """Returns programmed features by FEN; records each (fen, white_perspective) call."""

    def __init__(self, by_fen: dict[str, dict]) -> None:
        self._by_fen = by_fen
        self.calls: list[tuple[str, bool]] = []

    def extract(self, fen: str, *, white_perspective: bool) -> dict:
        self.calls.append((fen, white_perspective))
        return self._by_fen[fen]


def test_push_uci_matches_python_chess():
    b = chess.Board()
    b.push_uci("e2e4")
    assert push_uci(chess.STARTING_FEN, "e2e4") == b.fen()


def test_feature_diff_arithmetic_and_perspective():
    played_fen = push_uci(FEN_BLACK_TO_MOVE, "g8f6")
    best_fen = push_uci(FEN_BLACK_TO_MOVE, "g8e7")
    fake = FakeExtractor(
        {
            played_fen: _feat(mobility=10, isolated_pawns=2, king_shield=1),
            best_fen: _feat(mobility=14, isolated_pawns=0, king_shield=3),
        }
    )

    diff = feature_diff(
        FEN_BLACK_TO_MOVE, "g8f6", "g8e7", mover_white=False, extractor=fake
    )

    assert diff.delta["mobility"] == -4  # played gives up 4 squares of mobility vs best
    assert diff.delta["isolated_pawns"] == 2  # played leaves 2 isolated pawns best avoids
    assert diff.delta["king_shield"] == -2  # played weakens the shield
    # Both resulting positions scored from the mover's (Black's) perspective, exactly once each.
    assert sorted(f for f, _ in fake.calls) == sorted([played_fen, best_fen])
    assert all(persp is False for _, persp in fake.calls)


def test_identical_moves_give_zero_delta():
    f = push_uci(chess.STARTING_FEN, "e2e4")
    fake = FakeExtractor({f: _feat(mobility=5)})
    diff = feature_diff(
        chess.STARTING_FEN, "e2e4", "e2e4", mover_white=True, extractor=fake
    )
    assert all(v == 0 for v in diff.delta.values())
    assert diff.played["mobility"] == 5
    assert diff.played_archetype == "unknown"
