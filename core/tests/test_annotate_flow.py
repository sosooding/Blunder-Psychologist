"""Annotation-assembly tests — pure, with a fake extractor (no DB, no LLM, no model)."""

import chess

from blunder.annotate_flow import (
    build_annotation_inputs,
    detect_motifs,
    signature_text,
    uci_line_to_san,
)
from blunder.featurediff import push_uci
from tests.test_featurediff import FakeExtractor, _feat

# Black to move, knight on d2. ...Ne4 hangs it to Re1 (king on e8 behind), and the knight's new
# square is far worse than a quiet retreat.
FEN = "4k3/8/8/8/8/8/3n4/4R1K1 b - - 0 1"


def test_uci_line_to_san_renders_line():
    assert uci_line_to_san(chess.STARTING_FEN, ["e2e4", "e7e5", "g1f3"]) == ["e4", "e5", "Nf3"]
    assert uci_line_to_san(chess.STARTING_FEN, ["e2e4"], max_plies=0) == []


def test_uci_line_to_san_stops_on_illegal():
    assert uci_line_to_san(chess.STARTING_FEN, ["e2e4", "h1h8"]) == ["e4"]


def test_signature_text_shape():
    s = signature_text("middlegame", "iqp", ["structure_damage", "mobility_collapse"])
    assert "middlegame" in s and "iqp" in s
    assert "mobility_collapse" in s and "structure_damage" in s
    s2 = signature_text("opening", "unknown", [], description="dropped a pawn")
    assert "none" in s2 and "dropped a pawn" in s2


def test_detect_motifs_combines_families():
    best_uci = "d2c4"
    fake = FakeExtractor(
        {
            push_uci(FEN, "d2e4"): _feat(mobility=2),  # played: collapsed mobility
            push_uci(FEN, best_uci): _feat(mobility=12),  # best: healthy
        }
    )
    motifs = detect_motifs({"fen": FEN, "move": "Ne4", "best_pv": [best_uci]}, fake)
    assert "hanging_piece" in motifs  # tactical
    assert "mobility_collapse" in motifs  # positional
    assert motifs == sorted(motifs)


def test_detect_motifs_without_best_pv_is_tactical_only():
    # No best move → positional diff is skipped; the extractor must not be called. ...Ne4 both
    # hangs the knight and pins it to the e8 king (Re1), so both tactical tags fire.
    fake = FakeExtractor({})
    motifs = detect_motifs({"fen": FEN, "move": "Ne4", "best_pv": []}, fake)
    assert motifs == ["hanging_piece", "pin"]
    assert fake.calls == []


def test_build_annotation_inputs_maps_rows():
    best_uci = "d2c4"
    fake = FakeExtractor(
        {push_uci(FEN, "d2e4"): _feat(mobility=2), push_uci(FEN, best_uci): _feat(mobility=12)}
    )
    rows = [
        {
            "id": 42,
            "fen": FEN,
            "move": "Ne4",
            "best_pv": [best_uci],
            "eval_cp": -300,
            "delta_cp": 350,
            "phase": "endgame",
            "archetype": "endgame_simplified",
            "clock_seconds": 40,
        }
    ]
    inputs, detected, bids = build_annotation_inputs(rows, fake)
    assert bids == [42]
    assert inputs[0].played_san == "Ne4"
    assert inputs[0].delta_cp == 350
    assert inputs[0].archetype == "endgame_simplified"
    assert detected[0] == inputs[0].detected_motifs
    assert {"hanging_piece", "mobility_collapse"} <= set(detected[0])
