"""Tactical motif detectors.

These run on the position *immediately after the blunder* — the side to move is the one who gets
to punish it (exactly the Lichess-puzzle convention, which is what the benchmark fixtures are).
The blunderer is ``board.turn``'s opponent; we call them the *victim*. A motif fires when the
geometry of the punishment is present; the engine eval is what flags the move as a blunder in the
first place, so the detector only has to explain *which* tactic the move walked into.

Detection is static (python-chess move enumeration + a static-exchange evaluator), so it needs no
engine PV and is fully unit-testable offline. ``overloaded_defender`` and ``missed_break`` are in
the vocabulary but not yet detected.
"""

import chess

# Centipawn piece values for static exchange evaluation and "is this worth winning" thresholds.
PIECE_VALUE = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20000,
}

# A capture/fork is "material-winning" once it nets at least a minor piece minus a pawn.
WINNING_CP = 200
MINOR = 300  # value floor for a "valuable" forked target


def _gain(board: chess.Board, to_sq: int) -> int:
    """Best material (cp, ≥ 0) the side to move can win by capturing on ``to_sq``.

    Recursive static exchange: the side to move may decline to capture (hence ``max(0, …)``), and
    otherwise picks the capture maximising its net — legality is re-checked at each ply so a pinned
    attacker can't participate.
    """
    target = board.piece_type_at(to_sq)
    if target is None:
        return 0
    best = 0
    for atk_sq in board.attackers(board.turn, to_sq):
        move = chess.Move(atk_sq, to_sq)
        if not board.is_legal(move):
            continue
        board.push(move)
        net = PIECE_VALUE[target] - _gain(board, to_sq)
        board.pop()
        best = max(best, net)
    return max(best, 0)


def see_capture(board: chess.Board, move: chess.Move) -> int:
    """Static exchange value (cp) of a capture, from the capturing side's perspective."""
    captured = board.piece_type_at(move.to_square)
    if captured is None:
        return 0
    board.push(move)
    value = PIECE_VALUE[captured] - _gain(board, move.to_square)
    board.pop()
    return value


def _winning_captures(board: chess.Board) -> list[tuple[chess.Move, int]]:
    """Legal captures for the side to move whose SEE clears ``WINNING_CP``."""
    out = []
    for move in board.legal_moves:
        if board.is_capture(move):
            v = see_capture(board, move)
            if v >= WINNING_CP:
                out.append((move, v))
    return out


def _detect_hanging(board: chess.Board) -> bool:
    """The blunder left a piece en prise: the side to move can win material by a capture."""
    return bool(_winning_captures(board))


def _detect_fork(board: chess.Board, victim: chess.Color) -> bool:
    """A single move by the side to move attacks ≥2 valuable victim targets (king counts), where
    the forking piece can't simply be won back — otherwise it's a sac, not a fork."""
    for move in board.legal_moves:
        board.push(move)  # victim to move now; the forker sits on `landed`
        landed = move.to_square
        targets = 0
        for sq in board.attacks(landed):
            piece = board.piece_at(sq)
            if piece is None or piece.color != victim:
                continue
            if piece.piece_type == chess.KING or PIECE_VALUE[piece.piece_type] >= MINOR:
                targets += 1
        forker_winnable = _gain(board, landed) >= WINNING_CP
        board.pop()
        if targets >= 2 and not forker_winnable:
            return True
    return False


def _detect_pin(board: chess.Board, victim: chess.Color) -> bool:
    """A valuable victim piece is absolutely pinned to its king."""
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece is None or piece.color != victim:
            continue
        if piece.piece_type in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
            if board.is_pinned(victim, sq):
                return True
    return False


def _detect_back_rank(board: chess.Board, victim: chess.Color) -> bool:
    """The side to move has a back-rank checkmate with a rook/queen against the victim king."""
    back_rank = 0 if victim == chess.WHITE else 7
    king_sq = board.king(victim)
    if king_sq is None or chess.square_rank(king_sq) != back_rank:
        return False
    for move in board.legal_moves:
        mover = board.piece_type_at(move.from_square)
        if mover not in (chess.ROOK, chess.QUEEN):
            continue
        if chess.square_rank(move.to_square) != back_rank:
            continue
        board.push(move)
        mate = board.is_checkmate()
        board.pop()
        if mate:
            return True
    return False


def detect_tactical(board: chess.Board) -> set[str]:
    """Tactical motif tags for the position right after a blunder (side to move = the punisher)."""
    victim = not board.turn
    tags: set[str] = set()
    if _detect_hanging(board):
        tags.add("hanging_piece")
    if _detect_fork(board, victim):
        tags.add("fork")
    if _detect_pin(board, victim):
        tags.add("pin")
    if _detect_back_rank(board, victim):
        tags.add("back_rank")
    return tags


def detect_tactical_for_move(fen_before: str, played_uci: str) -> set[str]:
    """Bridge from a candidate (the position faced + the move played) to the post-blunder board the
    detectors expect. This is the entry point the funnel uses on a ``DeepResult``."""
    board = chess.Board(fen_before)
    board.push(chess.Move.from_uci(played_uci))
    return detect_tactical(board)
