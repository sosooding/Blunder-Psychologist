#pragma once

#include "chess.hpp"

// Pawn-structure bitboard predicates over a chess::Board. Pure board geometry — no engine,
// no I/O, no Stockfish — so this whole feature layer builds and tests on any platform.
//
// Orientation convention: "ahead" is always toward the enemy back rank — north (higher rank)
// for White, south (lower rank) for Black. Every predicate is colour-relative.
namespace blunder {

using chess::Bitboard;
using chess::Board;
using chess::Color;
using chess::File;
using chess::PieceType;
using chess::Square;

// All squares on a file.
Bitboard fileBB(File f);
// Union of the files immediately left and right of f (its neighbour files; empty edges drop out).
Bitboard adjacentFiles(File f);

// Friendly pawns of a colour.
Bitboard pawns(const Board& b, Color c);

// The "passed-pawn span": every square ahead of sq on its own file and both neighbour files.
// A pawn is passed iff no enemy pawn occupies this span.
Bitboard passedSpan(Color c, Square sq);

// --- pawn-set predicates: each returns the subset of `c`'s pawns with the property ----------

// No friendly pawn on either neighbour file.
Bitboard isolatedPawns(const Board& b, Color c);
// Shares its file with at least one other friendly pawn (all such pawns are returned).
Bitboard doubledPawns(const Board& b, Color c);
// No enemy pawn anywhere on its file or neighbour files ahead, and no friendly pawn blocking
// ahead on its own file.
Bitboard passedPawns(const Board& b, Color c);
// Cannot be defended onto its stop square by a friendly pawn (no friendly pawn on a neighbour
// file at or behind its rank), and its stop square is controlled by an enemy pawn — so it is
// stuck and weak.
Bitboard backwardPawns(const Board& b, Color c);

// --- file state -----------------------------------------------------------------------------

// No pawn of either colour on the file.
bool isOpenFile(const Board& b, File f);
// No friendly pawn but at least one enemy pawn on the file (half-open for `c`).
bool isHalfOpenFile(const Board& b, Color c, File f);
int openFileCount(const Board& b);
int halfOpenFileCount(const Board& b, Color c);

// --- king shield ----------------------------------------------------------------------------

// Of the up-to-three files spanning the king (king file +/- 1), how many carry a friendly pawn
// within two ranks ahead of the king. 3 = intact shield, 0 = fully exposed.
int kingShield(const Board& b, Color c);

}  // namespace blunder
