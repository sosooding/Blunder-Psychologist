#include "blunder/features.hpp"

#include <cstdint>
#include <sstream>
#include <string>

#include "blunder/pawns.hpp"
#include "chess.hpp"

namespace blunder {

namespace {

using chess::Bitboard;
using chess::Board;
using chess::Color;
using chess::PieceType;
using chess::Square;
using chess::attacks;

// Union of every square the perspective's minor and major pieces attack.
Bitboard pieceAttacks(const Board& b, Color c) {
    const Bitboard occ = b.occ();
    Bitboard atk(0ULL);
    Bitboard knights = b.pieces(PieceType::KNIGHT, c);
    while (knights) atk |= attacks::knight(Square(knights.pop()));
    Bitboard bishops = b.pieces(PieceType::BISHOP, c);
    while (bishops) atk |= attacks::bishop(Square(bishops.pop()), occ);
    Bitboard rooks = b.pieces(PieceType::ROOK, c);
    while (rooks) atk |= attacks::rook(Square(rooks.pop()), occ);
    Bitboard queens = b.pieces(PieceType::QUEEN, c);
    while (queens) atk |= attacks::queen(Square(queens.pop()), occ);
    return atk;
}

// Every square the perspective's pawns attack.
Bitboard pawnAttacks(const Board& b, Color c) {
    Bitboard atk(0ULL);
    Bitboard p = pawns(b, c);
    while (p) atk |= attacks::pawn(c, Square(p.pop()));
    return atk;
}

// Count distinct enemy pieces (any type but the king) bearing on the king's zone.
int kingZoneAttackers(const Board& b, Color c) {
    const Square ksq = b.kingSq(c);
    const Bitboard zone = attacks::king(ksq) | Bitboard::fromSquare(ksq);
    const Color e = ~c;
    const Bitboard occ = b.occ();

    int n = 0;
    Bitboard pw = b.pieces(PieceType::PAWN, e);
    while (pw)
        if (!(attacks::pawn(e, Square(pw.pop())) & zone).empty()) ++n;
    Bitboard kn = b.pieces(PieceType::KNIGHT, e);
    while (kn)
        if (!(attacks::knight(Square(kn.pop())) & zone).empty()) ++n;
    Bitboard bi = b.pieces(PieceType::BISHOP, e);
    while (bi)
        if (!(attacks::bishop(Square(bi.pop()), occ) & zone).empty()) ++n;
    Bitboard ro = b.pieces(PieceType::ROOK, e);
    while (ro)
        if (!(attacks::rook(Square(ro.pop()), occ) & zone).empty()) ++n;
    Bitboard qu = b.pieces(PieceType::QUEEN, e);
    while (qu)
        if (!(attacks::queen(Square(qu.pop()), occ) & zone).empty()) ++n;
    return n;
}

// --- minimal JSON helpers for our own flat schema (round-trip only) -------------------------

std::size_t valueStart(const std::string& j, const std::string& key) {
    const std::string k = "\"" + key + "\"";
    std::size_t pos = j.find(k);
    if (pos == std::string::npos) return std::string::npos;
    pos = j.find(':', pos + k.size());
    if (pos == std::string::npos) return std::string::npos;
    return pos + 1;
}

int intField(const std::string& j, const std::string& key) {
    const std::size_t p = valueStart(j, key);
    if (p == std::string::npos) return 0;
    return std::stoi(j.substr(p));
}

std::string strField(const std::string& j, const std::string& key) {
    const std::size_t p = valueStart(j, key);
    if (p == std::string::npos) return "";
    const std::size_t q1 = j.find('"', p);
    const std::size_t q2 = j.find('"', q1 + 1);
    return j.substr(q1 + 1, q2 - q1 - 1);
}

}  // namespace

Features extractFeatures(const Board& b, Color perspective) {
    Features f;
    const Color c = perspective;

    f.isolated_pawns = isolatedPawns(b, c).count();
    f.doubled_pawns = doubledPawns(b, c).count();
    f.backward_pawns = backwardPawns(b, c).count();
    f.passed_pawns = passedPawns(b, c).count();

    f.open_files = openFileCount(b);
    f.half_open_files = halfOpenFileCount(b, c);

    f.king_shield = kingShield(b, c);
    f.king_zone_attackers = kingZoneAttackers(b, c);

    const std::uint64_t enemy_half =
        c == Color::WHITE ? 0xFFFFFFFF00000000ULL : 0x00000000FFFFFFFFULL;
    f.space = (pawnAttacks(b, c) & Bitboard(enemy_half)).count();
    f.mobility = (pieceAttacks(b, c) & ~b.us(c)).count();

    f.archetype = classify(b);
    return f;
}

std::string toJson(const Features& f) {
    std::ostringstream os;
    os << '{' << "\"isolated_pawns\":" << f.isolated_pawns << ",\"doubled_pawns\":"
       << f.doubled_pawns << ",\"backward_pawns\":" << f.backward_pawns
       << ",\"passed_pawns\":" << f.passed_pawns << ",\"open_files\":" << f.open_files
       << ",\"half_open_files\":" << f.half_open_files << ",\"king_shield\":" << f.king_shield
       << ",\"king_zone_attackers\":" << f.king_zone_attackers << ",\"space\":" << f.space
       << ",\"mobility\":" << f.mobility << ",\"archetype\":\"" << archetypeName(f.archetype)
       << "\"}";
    return os.str();
}

Features featuresFromJson(const std::string& j) {
    Features f;
    f.isolated_pawns = intField(j, "isolated_pawns");
    f.doubled_pawns = intField(j, "doubled_pawns");
    f.backward_pawns = intField(j, "backward_pawns");
    f.passed_pawns = intField(j, "passed_pawns");
    f.open_files = intField(j, "open_files");
    f.half_open_files = intField(j, "half_open_files");
    f.king_shield = intField(j, "king_shield");
    f.king_zone_attackers = intField(j, "king_zone_attackers");
    f.space = intField(j, "space");
    f.mobility = intField(j, "mobility");
    f.archetype = archetypeFromName(strField(j, "archetype"));
    return f;
}

}  // namespace blunder
