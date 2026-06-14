"""Pure test for the deep-pass row builder — confirms best_pv is persisted (no DB)."""

import json

import chess

from blunder.deep import move_analysis_params
from blunder.engine import DeepResult
from blunder.ingest import ParsedGame, ParsedMove


def test_move_analysis_params_includes_best_pv():
    move = ParsedMove(
        ply=0,
        fen_before=chess.STARTING_FEN,
        san="e4",
        uci="e2e4",
        color=chess.WHITE,
        is_user_move=True,
        eval_cp=20,
        clock_seconds=30,
    )
    pg = ParsedGame(
        lichess_id="x",
        pgn="",
        time_control=None,
        played_at=None,
        speed=None,
        user_color=chess.WHITE,
        moves=[move],
    )
    r = DeepResult(
        fen=chess.STARTING_FEN,
        move_uci="e2e4",
        move_san="e4",
        white_to_move=True,
        eval_cp=20,
        best_eval_cp=30,
        delta_cp=10,
        sharpness=5,
        severity="inaccuracy",
        archetype="unknown",
        features={"mobility": 1},
        best_pv=["e2e4", "e7e5"],
    )
    params = move_analysis_params(7, pg, 0, r)
    assert params["gid"] == 7
    assert params["best_pv"] == json.dumps(["e2e4", "e7e5"])
    assert params["features"] == json.dumps({"mobility": 1})
    assert params["sharpness"] == 5.0
