"""Post-build smoke test for the ``blunder_engine`` wheel.

Run after ``pip install ./engine`` with a Stockfish binary reachable (``STOCKFISH_PATH`` or on
``PATH``). Confirms the native module imports and that the Scholar's-mate blunder is detected,
and that analysis is deterministic across pool sizes through the Python boundary.
"""

import blunder_engine as be

PGN = "\n".join(
    [
        '[Event "Smoke"]',
        '[White "W"]',
        '[Black "B"]',
        '[Result "1-0"]',
        "",
        "1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0",
        "",
    ]
)


def main() -> None:
    games = be.analyze_games([PGN], nodes=120_000, multipv=3)
    assert len(games) == 1, f"expected 1 game, got {len(games)}"

    moves = games[0].moves
    assert len(moves) == 7, f"expected 7 plies, got {len(moves)}"

    worst = max(moves, key=lambda m: m.delta_cp)
    assert worst.move_uci == "g8f6", f"worst move was {worst.move_uci}, expected g8f6 (Nf6)"
    assert worst.delta_cp >= 5000, f"blunder delta too small: {worst.delta_cp}"
    assert worst.eval_cp >= 5000, f"eval should flip to White mating: {worst.eval_cp}"

    # Deterministic regardless of how many engine processes do the work.
    a = be.serialize(be.analyze_games([PGN], nodes=100_000, multipv=3, engines=1))
    b = be.serialize(be.analyze_games([PGN], nodes=100_000, multipv=3, engines=2))
    assert a == b, "analysis was not deterministic across pool sizes"

    # Stockfish-free feature extraction (used by the positional motif detectors). White has an
    # isolated, passed-looking d4 pawn and an intact king shield.
    import json

    feats = json.loads(
        be.extract_features("r2q1rk1/pp3ppp/2n1pn2/8/3P4/2N2N2/PP3PPP/R1BQ1RK1 w - - 0 1", True)
    )
    assert feats["isolated_pawns"] == 1, f"expected 1 isolated pawn, got {feats}"
    assert feats["king_shield"] == 3, f"expected intact king shield, got {feats}"
    assert feats["archetype"] == "iqp", f"expected iqp archetype, got {feats['archetype']}"

    print(f"smoke OK: {worst!r}; features OK: {feats}")


if __name__ == "__main__":
    main()
