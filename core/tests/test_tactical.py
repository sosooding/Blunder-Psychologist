"""Tactical detector benchmark — pure (no DB, no engine).

The committed fixtures are a hand-built starter set, one motif isolated per position plus quiet
controls, so we can assert both recall (the expected tag fires) and precision (nothing else does).
Expand by sampling the Lichess puzzle database via vocab.LICHESS_THEME_MAP — that data is not
committed; only the derived fixtures are.
"""

import json
from collections import defaultdict
from pathlib import Path

import chess

from blunder.motifs.tactical import detect_tactical, detect_tactical_for_move
from blunder.motifs.vocab import TACTICAL_TAGS

FIXTURES = Path(__file__).parent / "fixtures" / "tactical_fixtures.json"


def _fixtures() -> list[dict]:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


def test_fixtures_match_exactly():
    """Recall + precision: each curated position yields exactly its expected tag set."""
    for fx in _fixtures():
        got = detect_tactical(chess.Board(fx["fen"]))
        assert got == set(fx["expected_tags"]), f"{fx['note']}: got {got}"


def test_detected_tags_stay_in_vocabulary():
    for fx in _fixtures():
        assert detect_tactical(chess.Board(fx["fen"])) <= TACTICAL_TAGS


def test_for_move_bridges_to_post_move_board():
    fen_before = "k7/8/8/8/4n3/8/8/4R1K1 b - - 0 1"  # Black to move, knight on e4
    board = chess.Board(fen_before)
    board.push(chess.Move.from_uci("e4d2"))
    assert detect_tactical_for_move(fen_before, "e4d2") == detect_tactical(board)


def test_every_detected_motif_has_a_fixture():
    """Per-motif recall floor: every motif we actually detect is exercised by ≥1 fixture."""
    seen: dict[str, int] = defaultdict(int)
    for fx in _fixtures():
        for tag in fx["expected_tags"]:
            seen[tag] += 1
    for motif in ("hanging_piece", "fork", "pin", "back_rank"):
        assert seen[motif] >= 1, f"no fixture covers {motif}"
