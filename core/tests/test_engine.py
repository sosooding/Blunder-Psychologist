"""Engine-seam and deep-pass unit tests — pure parts only (no wheel, no DB).

The native engine and DB writes are covered by the in-container integration test."""

import io

import chess
import chess.pgn

from blunder.deep import move_analysis_params, scan_user_moves
from blunder.engine import DeepResult, candidate_pgn, classify_phase, is_flagged
from blunder.ingest import ParsedGame, ParsedMove


def _dr(uci, *, delta=0, severity="none", **kw):
    base = dict(
        fen="-", move_uci=uci, move_san="x", white_to_move=True,
        eval_cp=0, best_eval_cp=0, delta_cp=delta, sharpness=0,
        severity=severity, archetype="unknown", features={}, best_pv=[],
    )
    base.update(kw)
    return DeepResult(**base)


class FakeAnalyzer:
    """Returns a canned DeepResult per move UCI, aligned to input order."""

    def __init__(self, by_uci: dict[str, DeepResult | None]):
        self._by_uci = by_uci
        self.calls: list[tuple] = []

    def analyze(self, positions, *, nodes, multipv=3):
        self.calls.append((list(positions), nodes, multipv))
        return [self._by_uci.get(uci) for _fen, uci in positions]


def test_candidate_pgn_round_trips_fen_and_move():
    fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"  # after 1.e4, Black to move
    pgn = candidate_pgn(fen, "c7c5")
    assert '[SetUp "1"]' in pgn
    assert '[FEN "' in pgn  # start position carried in the headers

    game = chess.pgn.read_game(io.StringIO(pgn))
    # setup() normalises the FEN (drops the irrelevant e.p. square); compare against the same
    # normalisation, which is exactly what ingest stores too, so positions stay consistent.
    assert game.board().fen() == chess.Board(fen).fen()
    moves = list(game.mainline_moves())
    assert len(moves) == 1
    assert moves[0].uci() == "c7c5"


def test_classify_phase():
    start = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    assert classify_phase(start) == "opening"
    # King-and-pawn endgame: no minor/major pieces.
    assert classify_phase("8/5k2/8/8/8/3K4/4P3/8 w - - 0 50") == "endgame"
    # Lots of material, well past move 12 -> middlegame.
    mid = "r1bq1rk1/pppp1ppp/2n2n2/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQ1RK1 w - - 0 13"
    assert classify_phase(mid) == "middlegame"


def test_is_flagged():
    assert is_flagged(_dr("e2e4", severity="blunder"))
    assert is_flagged(_dr("e2e4", severity="inaccuracy"))
    assert not is_flagged(_dr("e2e4", severity="none"))
    assert not is_flagged(_dr("e2e4", severity=""))


def test_move_analysis_params_builds_row():
    moves = [
        ParsedMove(0, "fen0", "e4", "e2e4", chess.WHITE, True, 20, 600),
        ParsedMove(
            1,
            "r1bq1rk1/pppp1ppp/2n2n2/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQ1RK1 w - - 0 13",
            "Bxf7+", "c4f7", chess.WHITE, True, 250, 540,
        ),
    ]
    pg = ParsedGame("g1", "pgn", "600+0", None, "rapid", chess.WHITE, moves)
    r = _dr("c4f7", delta=300, severity="blunder", eval_cp=-50, best_eval_cp=250,
            sharpness=40, archetype="iqp", features={"space": 3})

    params = move_analysis_params(7, pg, 1, r)
    assert params["gid"] == 7
    assert params["ply"] == 1
    assert params["fen"].startswith("r1bq1rk1")
    assert params["move"] == "Bxf7+"
    assert params["delta_cp"] == 300
    assert params["best_eval_cp"] == 250
    assert params["sharpness"] == 40.0
    assert params["clock"] == 540
    assert params["phase"] == "middlegame"
    assert params["arch"] == "iqp"
    assert params["features"] == '{"space": 3}'  # JSON-encoded for the JSONB column


def test_scan_user_moves_flags_over_threshold():
    moves = [
        ParsedMove(0, "fenA", "Nf3", "g1f3", chess.WHITE, True, None, None),
        ParsedMove(1, "fenB", "h6", "h7h6", chess.BLACK, False, None, None),
        ParsedMove(2, "fenC", "Qd2", "d1d2", chess.WHITE, True, None, None),
    ]
    pg = ParsedGame("g", "pgn", None, None, "rapid", chess.WHITE, moves)
    analyzer = FakeAnalyzer(
        {"g1f3": _dr("g1f3", delta=40), "d1d2": _dr("d1d2", delta=220)}
    )

    cands = scan_user_moves(pg, [0, 2], analyzer, nodes=100_000, threshold=100)
    assert [(c.ply, c.loss_cp, c.source) for c in cands] == [(2, 220, "engine_scan")]
    # Scanned exactly the requested plies at the low node budget.
    positions, nodes, _ = analyzer.calls[0]
    assert nodes == 100_000
    assert positions == [("fenA", "g1f3"), ("fenC", "d1d2")]


def test_scan_user_moves_empty_is_noop():
    pg = ParsedGame("g", "pgn", None, None, "rapid", chess.WHITE, [])
    analyzer = FakeAnalyzer({})
    assert scan_user_moves(pg, [], analyzer) == []
    assert analyzer.calls == []
