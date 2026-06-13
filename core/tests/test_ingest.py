"""PGN parsing tests — pure, against the committed NDJSON fixture (no DB, no network)."""

import json
from pathlib import Path

import chess
import pytest

from blunder.ingest import parse_game, parse_pgn

FIXTURES = Path(__file__).parent / "fixtures"
START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


@pytest.fixture(scope="module")
def records() -> dict[str, dict]:
    out = {}
    for line in (FIXTURES / "user_games.ndjson").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[r["id"]] = r
    return out


def test_parses_metadata_and_user_as_white(records):
    pg = parse_game(records["g0000001"], "alice")
    assert pg.lichess_id == "g0000001"
    assert pg.user_color == chess.WHITE
    assert pg.time_control == "600+0"
    assert pg.speed == "rapid"
    assert pg.played_at is not None and pg.played_at.tzinfo is not None
    assert len(pg.moves) == 16
    assert pg.moves[0].fen_before == START_FEN
    assert pg.moves[0].color == chess.WHITE


def test_per_move_eval_clock_and_user_flag(records):
    pg = parse_game(records["g0000001"], "alice")
    b5 = pg.moves[11]  # black's 6th move ...b5, the blunder in the fixture
    assert b5.san == "b5"
    assert b5.color == chess.BLACK
    assert b5.is_user_move is False  # user is White here
    assert b5.eval_cp == 320  # [%eval 3.2] -> White-POV centipawns
    assert b5.clock_seconds == 9 * 60 + 20  # [%clk 0:09:20]


def test_user_as_black_flags_their_moves(records):
    pg = parse_game(records["g0000002"], "alice")
    assert pg.user_color == chess.BLACK
    assert pg.time_control == "1800+0"
    ne4 = pg.moves[9]  # alice (Black) blunders ...Ne4
    assert ne4.san == "Ne4"
    assert ne4.is_user_move is True
    assert ne4.eval_cp == 260
    # White moves are not the user's.
    assert all(not m.is_user_move for m in pg.moves if m.color == chess.WHITE)


def test_username_match_is_case_insensitive(records):
    assert parse_game(records["g0000001"], "ALICE").user_color == chess.WHITE


def test_unknown_user_yields_no_user_moves(records):
    pg = parse_game(records["g0000001"], "stranger")
    assert pg.user_color is None
    assert all(not m.is_user_move for m in pg.moves)


def test_parse_pgn_derives_everything_from_headers(records):
    # scan/deep re-parse from the stored PGN alone (no NDJSON record).
    pgn = records["g0000002"]["pgn"]
    pg = parse_pgn(pgn, "alice")
    assert pg.lichess_id == "g0000002"  # from [Site "https://lichess.org/g0000002"]
    assert pg.user_color == chess.BLACK  # from [Black "alice"]
    assert pg.time_control == "1800+0"  # from [TimeControl]
    assert pg.speed == "classical"  # parsed from the Event header
    assert pg.played_at is not None and pg.played_at.year == 2026  # from [UTCDate]
    assert pg.moves[9].san == "Ne4" and pg.moves[9].is_user_move is True


def test_mate_eval_maps_to_large_cp():
    record = {
        "id": "mate1",
        "speed": "rapid",
        "createdAt": 1_700_000_000_000,
        "players": {"white": {"user": {"name": "alice"}}, "black": {"user": {"name": "bob"}}},
        "pgn": '[White "alice"]\n[Black "bob"]\n\n1. f3 { [%eval 0.0] } e5 { [%eval 0.1] } '
        "2. g4 { [%eval -0.2] } Qh4# { [%eval #-0] } 0-1\n",
    }
    pg = parse_game(record, "alice")
    assert pg.moves[-1].san == "Qh4#"
    assert pg.moves[-1].eval_cp is not None and pg.moves[-1].eval_cp <= -9000
