"""Cheap-pass tests — pure. Uses the fixture games plus synthetic move lists for edge cases."""

import json
from pathlib import Path

import chess

from blunder.funnel import cheap_pass, loss_cp
from blunder.ingest import ParsedMove, parse_game

FIXTURES = Path(__file__).parent / "fixtures"


def _records() -> dict[str, dict]:
    out = {}
    for line in (FIXTURES / "user_games.ndjson").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[r["id"]] = r
    return out


def _m(ply, color, is_user, eval_cp):
    return ParsedMove(
        ply=ply, fen_before="-", san="x", uci="x", color=color,
        is_user_move=is_user, eval_cp=eval_cp, clock_seconds=None,
    )


def test_loss_cp_perspective():
    # White lost a pawn: eval fell from +50 to -50 -> loss 100.
    assert loss_cp(50, -50, chess.WHITE) == 100
    # Black lost a pawn: eval rose from -50 to +50 -> loss 100.
    assert loss_cp(-50, 50, chess.BLACK) == 100
    # An improving move is negative loss.
    assert loss_cp(0, 80, chess.WHITE) == -80


def test_flags_user_blunder_from_fixture_black():
    pg = parse_game(_records()["g0000002"], "alice")  # alice is Black, blunders ...Ne4 at ply 9
    cands, needs_scan = cheap_pass(pg.moves, book_exit_ply=0)
    assert needs_scan == []
    assert [c.ply for c in cands] == [9]
    assert cands[0].loss_cp == 280  # -20 -> +260 from Black's perspective
    assert cands[0].source == "lichess_eval"


def test_opponent_blunder_is_not_flagged():
    # In g1 alice is White and clean; the only blunder (...b5, ply 11) is the opponent's.
    pg = parse_game(_records()["g0000001"], "alice")
    cands, needs_scan = cheap_pass(pg.moves, book_exit_ply=0)
    assert cands == []
    assert needs_scan == []


def test_pre_book_user_moves_are_skipped():
    pg = parse_game(_records()["g0000002"], "alice")
    # Move the book exit past the ply-9 blunder; nothing should be flagged.
    cands, _ = cheap_pass(pg.moves, book_exit_ply=10)
    assert cands == []


def test_missing_evals_go_to_engine_scan_list():
    moves = [
        _m(0, chess.WHITE, True, 20),
        _m(1, chess.BLACK, False, 10),
        _m(2, chess.WHITE, True, None),  # user move, no eval on the move
        _m(3, chess.BLACK, False, 30),
        _m(4, chess.WHITE, True, 200),  # user move, but predecessor (ply3) has eval -> scorable
    ]
    cands, needs_scan = cheap_pass(moves, book_exit_ply=0, threshold=100)
    assert needs_scan == [2]
    # ply4: before=30, after=200, White loss = 30-200 = -170 -> not a candidate
    assert cands == []


def test_decided_position_is_suppressed():
    moves = [
        _m(0, chess.WHITE, False, 700),  # already +7 for White (decided)
        _m(1, chess.WHITE, True, 300),   # user (White) "loses" 400cp, but pre-move eval > 600
    ]
    # ply1 before = eval[0] = 700 -> |before| > 600 -> suppressed.
    cands, needs_scan = cheap_pass(moves, book_exit_ply=0, threshold=100)
    assert cands == []
    assert needs_scan == []


def test_threshold_boundary():
    moves = [
        _m(0, chess.WHITE, False, 0),
        _m(1, chess.WHITE, True, -100),  # White loss = 0 - (-100) = 100 == threshold
    ]
    cands, _ = cheap_pass(moves, book_exit_ply=0, threshold=100)
    assert [c.ply for c in cands] == [1]
    cands, _ = cheap_pass(moves, book_exit_ply=0, threshold=101)
    assert cands == []
