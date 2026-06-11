#include "blunder/archetype.hpp"

#include <cstdint>

#include "blunder/pawns.hpp"
#include "chess.hpp"

namespace blunder {

namespace {

using chess::Bitboard;
using chess::Board;
using chess::Color;
using chess::File;
using chess::PieceType;
using chess::Square;

bool has(const Board& b, Color c, const char* square) {
    return pawns(b, c).check(Square(std::string_view(square)).index());
}

bool onFile(const Board& b, Color c, File::underlying f) {
    return !(pawns(b, c) & fileBB(File(f))).empty();
}

bool noneOnFile(const Board& b, Color c, File::underlying f) {
    return (pawns(b, c) & fileBB(File(f))).empty();
}

int count(const Board& b, PieceType pt) {
    return b.pieces(pt, Color::WHITE).count() + b.pieces(pt, Color::BLACK).count();
}

// --- archetype predicates -------------------------------------------------------------------

// Queens off and only a handful of pieces left: the position is an endgame, whatever the
// structure once was. Checked first as a phase gate.
bool isEndgameSimplified(const Board& b) {
    const int queens = count(b, PieceType::QUEEN);
    const int pieces = count(b, PieceType::KNIGHT) + count(b, PieceType::BISHOP) +
                       count(b, PieceType::ROOK) + queens;
    return queens == 0 && pieces <= 6;
}

// QGD Exchange: locked d4/d5, White's c-pawn and Black's e-pawn traded off, the other wing
// pawns (White e-, Black c-) still home — the classic minority-attack skeleton.
bool isCarlsbad(const Board& b) {
    return has(b, Color::WHITE, "d4") && has(b, Color::BLACK, "d5") &&
           noneOnFile(b, Color::WHITE, File::FILE_C) && noneOnFile(b, Color::BLACK, File::FILE_E) &&
           onFile(b, Color::WHITE, File::FILE_E) && onFile(b, Color::BLACK, File::FILE_C);
}

// The d5/e6/f5 (or d4/e3/f4) triangle with its hole on e5/e4.
bool isStonewall(const Board& b) {
    const bool black = has(b, Color::BLACK, "d5") && has(b, Color::BLACK, "e6") &&
                       has(b, Color::BLACK, "f5");
    const bool white = has(b, Color::WHITE, "d4") && has(b, Color::WHITE, "e3") &&
                       has(b, Color::WHITE, "f4");
    return black || white;
}

// The hedgehog spine: pawns on a6-b6-d6-e6 with the c-file conceded.
bool isHedgehog(const Board& b) {
    const bool black = has(b, Color::BLACK, "a6") && has(b, Color::BLACK, "b6") &&
                       has(b, Color::BLACK, "d6") && has(b, Color::BLACK, "e6") &&
                       noneOnFile(b, Color::BLACK, File::FILE_C);
    const bool white = has(b, Color::WHITE, "a3") && has(b, Color::WHITE, "b3") &&
                       has(b, Color::WHITE, "d3") && has(b, Color::WHITE, "e3") &&
                       noneOnFile(b, Color::WHITE, File::FILE_C);
    return black || white;
}

// The Maroczy bind: pawns on c4 and e4 clamping d5, no d-pawn, Black sitting on d6.
bool isMaroczy(const Board& b) {
    const bool white = has(b, Color::WHITE, "c4") && has(b, Color::WHITE, "e4") &&
                       noneOnFile(b, Color::WHITE, File::FILE_D) && has(b, Color::BLACK, "d6");
    const bool black = has(b, Color::BLACK, "c5") && has(b, Color::BLACK, "e5") &&
                       noneOnFile(b, Color::BLACK, File::FILE_D) && has(b, Color::WHITE, "d3");
    return white || black;
}

// An isolated d-pawn for one side with the d-file conceded by the other.
bool isIqp(const Board& b) {
    const bool white = !(isolatedPawns(b, Color::WHITE) & fileBB(File(File::FILE_D))).empty() &&
                       noneOnFile(b, Color::BLACK, File::FILE_D);
    const bool black = !(isolatedPawns(b, Color::BLACK) & fileBB(File(File::FILE_D))).empty() &&
                       noneOnFile(b, Color::WHITE, File::FILE_D);
    return white || black;
}

// Two friendly pawns abreast on c/d with the flanking b- and e-files conceded.
bool isHangingPawns(const Board& b) {
    const bool white = has(b, Color::WHITE, "c4") && has(b, Color::WHITE, "d4") &&
                       noneOnFile(b, Color::WHITE, File::FILE_B) &&
                       noneOnFile(b, Color::WHITE, File::FILE_E);
    const bool black = has(b, Color::BLACK, "c5") && has(b, Color::BLACK, "d5") &&
                       noneOnFile(b, Color::BLACK, File::FILE_B) &&
                       noneOnFile(b, Color::BLACK, File::FILE_E);
    return white || black;
}

// Advance-French chain: d4-e5 against d5-e6.
bool isFrenchChain(const Board& b) {
    return has(b, Color::WHITE, "d4") && has(b, Color::WHITE, "e5") && has(b, Color::BLACK, "d5") &&
           has(b, Color::BLACK, "e6");
}

// King's Indian chain: d5-e4 against e5-d6.
bool isKidChain(const Board& b) {
    return has(b, Color::WHITE, "d5") && has(b, Color::WHITE, "e4") && has(b, Color::BLACK, "e5") &&
           has(b, Color::BLACK, "d6");
}

bool isOppositeCastling(const Board& b) {
    const File wk = b.kingSq(Color::WHITE).file();
    const File bk = b.kingSq(Color::BLACK).file();
    const bool wq = wk <= File(File::FILE_C), wkside = wk >= File(File::FILE_F);
    const bool bq = bk <= File(File::FILE_C), bkside = bk >= File(File::FILE_F);
    return (wq && bkside) || (wkside && bq);
}

// Pawn skeletons that are exact vertical mirror images of each other.
bool isSymmetric(const Board& b) {
    const Bitboard wp = pawns(b, Color::WHITE);
    const Bitboard bp = pawns(b, Color::BLACK);
    if (wp.count() < 4) return false;  // too sparse to be a meaningful "structure"
    return __builtin_bswap64(wp.getBits()) == bp.getBits();
}

// A rammed central pawn (White pawn directly blocked by a Black pawn one rank ahead) marks a
// closed centre; its absence, an open one.
bool hasCentralRam(const Board& b) {
    const Bitboard wp = pawns(b, Color::WHITE);
    const Bitboard bp = pawns(b, Color::BLACK);
    for (int f = static_cast<int>(File::FILE_C); f <= static_cast<int>(File::FILE_F); ++f) {
        for (int r = 1; r <= 5; ++r) {
            if (wp.check(Square(File(f), chess::Rank(r)).index()) &&
                bp.check(Square(File(f), chess::Rank(r + 1)).index())) {
                return true;
            }
        }
    }
    return false;
}

}  // namespace

std::string archetypeName(Archetype a) {
    switch (a) {
        case Archetype::Carlsbad: return "carlsbad";
        case Archetype::Iqp: return "iqp";
        case Archetype::HangingPawns: return "hanging_pawns";
        case Archetype::Maroczy: return "maroczy";
        case Archetype::Hedgehog: return "hedgehog";
        case Archetype::Stonewall: return "stonewall";
        case Archetype::FrenchChain: return "french_chain";
        case Archetype::KidChain: return "kid_chain";
        case Archetype::SymmetricOpen: return "symmetric_open";
        case Archetype::SymmetricClosed: return "symmetric_closed";
        case Archetype::OppositeCastling: return "opposite_castling";
        case Archetype::EndgameSimplified: return "endgame_simplified";
        case Archetype::Unknown: break;
    }
    return "unknown";
}

Archetype archetypeFromName(const std::string& name) {
    for (int i = 0; i <= static_cast<int>(Archetype::Unknown); ++i) {
        const auto a = static_cast<Archetype>(i);
        if (archetypeName(a) == name) return a;
    }
    return Archetype::Unknown;
}

Archetype classify(const Board& b) {
    if (isEndgameSimplified(b)) return Archetype::EndgameSimplified;
    if (isCarlsbad(b)) return Archetype::Carlsbad;
    if (isStonewall(b)) return Archetype::Stonewall;
    if (isHedgehog(b)) return Archetype::Hedgehog;
    if (isMaroczy(b)) return Archetype::Maroczy;
    if (isIqp(b)) return Archetype::Iqp;
    if (isHangingPawns(b)) return Archetype::HangingPawns;
    if (isFrenchChain(b)) return Archetype::FrenchChain;
    if (isKidChain(b)) return Archetype::KidChain;
    if (isOppositeCastling(b)) return Archetype::OppositeCastling;
    if (isSymmetric(b)) return hasCentralRam(b) ? Archetype::SymmetricClosed
                                                : Archetype::SymmetricOpen;
    return Archetype::Unknown;
}

}  // namespace blunder
