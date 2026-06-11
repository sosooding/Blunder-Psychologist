#include "blunder/pawns.hpp"

#include <cstdint>

#include "chess.hpp"

namespace blunder {

namespace {

// Full-width mask of every square strictly ahead of rank r, from c's perspective.
std::uint64_t aheadRanks(Color c, int r) {
    if (c == Color::WHITE) return r >= 7 ? 0ULL : ~((1ULL << (8 * (r + 1))) - 1);
    return r <= 0 ? 0ULL : ((1ULL << (8 * r)) - 1);
}

// Full-width mask of every square on rank r or behind it, from c's perspective (own rank kept).
std::uint64_t behindOrEqualRanks(Color c, int r) {
    if (c == Color::WHITE) return r >= 7 ? ~0ULL : ((1ULL << (8 * (r + 1))) - 1);
    return r <= 0 ? ~0ULL : ~((1ULL << (8 * r)) - 1);
}

// The square directly in front of sq (its stop square). Returns NO_SQ off the board.
Square stopSquare(Color c, Square sq) {
    int idx = sq.index() + (c == Color::WHITE ? 8 : -8);
    if (idx < 0 || idx > 63) return Square(Square::NO_SQ);
    return Square(idx);
}

}  // namespace

Bitboard fileBB(File f) { return Bitboard(f); }

Bitboard adjacentFiles(File f) {
    int idx = static_cast<int>(f);
    Bitboard res(0ULL);
    if (idx > 0) res |= fileBB(File(idx - 1));
    if (idx < 7) res |= fileBB(File(idx + 1));
    return res;
}

Bitboard pawns(const Board& b, Color c) { return b.pieces(PieceType::PAWN, c); }

Bitboard passedSpan(Color c, Square sq) {
    Bitboard files = fileBB(sq.file()) | adjacentFiles(sq.file());
    return files & Bitboard(aheadRanks(c, static_cast<int>(sq.rank())));
}

Bitboard isolatedPawns(const Board& b, Color c) {
    const Bitboard p = pawns(b, c);
    Bitboard result(0ULL);
    Bitboard it = p;
    while (it) {
        const int s = it.pop();
        if ((p & adjacentFiles(Square(s).file())).empty()) result.set(s);
    }
    return result;
}

Bitboard doubledPawns(const Board& b, Color c) {
    const Bitboard p = pawns(b, c);
    Bitboard result(0ULL);
    for (int f = 0; f < 8; ++f) {
        const Bitboard on_file = p & fileBB(File(f));
        if (on_file.count() >= 2) result |= on_file;
    }
    return result;
}

Bitboard passedPawns(const Board& b, Color c) {
    const Bitboard own = pawns(b, c);
    const Bitboard enemy = pawns(b, ~c);
    Bitboard result(0ULL);
    Bitboard it = own;
    while (it) {
        const int s = it.pop();
        const Square sq(s);
        const bool blocked_by_own = !(own & fileBB(sq.file()) &
                                      Bitboard(aheadRanks(c, static_cast<int>(sq.rank()))))
                                         .empty();
        if (!blocked_by_own && (enemy & passedSpan(c, sq)).empty()) result.set(s);
    }
    return result;
}

Bitboard backwardPawns(const Board& b, Color c) {
    const Bitboard own = pawns(b, c);
    const Bitboard enemy = pawns(b, ~c);
    Bitboard result(0ULL);
    Bitboard it = own;
    while (it) {
        const int s = it.pop();
        const Square sq(s);

        // No friendly pawn on a neighbour file at or behind this pawn's rank can come to defend
        // its stop square — it is the rearmost of its little group.
        const Bitboard supporters = own & adjacentFiles(sq.file()) &
                                    Bitboard(behindOrEqualRanks(c, static_cast<int>(sq.rank())));
        if (!supporters.empty()) continue;

        // Its stop square is controlled by an enemy pawn, so it cannot safely advance.
        const Square stop = stopSquare(c, sq);
        if (!stop.is_valid()) continue;
        const bool stop_attacked = !(enemy & chess::attacks::pawn(c, stop)).empty();
        if (stop_attacked) result.set(s);
    }
    return result;
}

bool isOpenFile(const Board& b, File f) {
    return ((pawns(b, Color::WHITE) | pawns(b, Color::BLACK)) & fileBB(f)).empty();
}

bool isHalfOpenFile(const Board& b, Color c, File f) {
    return (pawns(b, c) & fileBB(f)).empty() && !(pawns(b, ~c) & fileBB(f)).empty();
}

int openFileCount(const Board& b) {
    int n = 0;
    for (int f = 0; f < 8; ++f)
        if (isOpenFile(b, File(f))) ++n;
    return n;
}

int halfOpenFileCount(const Board& b, Color c) {
    int n = 0;
    for (int f = 0; f < 8; ++f)
        if (isHalfOpenFile(b, c, File(f))) ++n;
    return n;
}

int kingShield(const Board& b, Color c) {
    const Square ksq = b.kingSq(c);
    const int kf = static_cast<int>(ksq.file());
    const int kr = static_cast<int>(ksq.rank());
    const Bitboard own = pawns(b, c);

    // The two ranks immediately ahead of the king.
    std::uint64_t two_ahead = 0ULL;
    for (int d = 1; d <= 2; ++d) {
        const int r = kr + (c == Color::WHITE ? d : -d);
        if (r >= 0 && r <= 7) two_ahead |= chess::Rank(r).bb();
    }

    int shield = 0;
    for (int f = kf - 1; f <= kf + 1; ++f) {
        if (f < 0 || f > 7) continue;
        if (!(own & fileBB(File(f)) & Bitboard(two_ahead)).empty()) ++shield;
    }
    return shield;
}

}  // namespace blunder
