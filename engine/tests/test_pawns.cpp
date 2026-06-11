// Per-predicate bitboard fixtures. Each position is hand-built so the expected pawns are
// unambiguous; the predicate semantics are pinned here before the classifier leans on them.

#include "blunder/pawns.hpp"
#include "catch_amalgamated.hpp"
#include "chess.hpp"

using namespace blunder;
using chess::Board;
using chess::Color;
using chess::File;
using chess::Square;

namespace {
int sq(const char* s) { return Square(std::string_view(s)).index(); }
bool only(const Bitboard& bb, std::initializer_list<const char*> squares) {
    Bitboard expected(0ULL);
    for (const char* s : squares) expected.set(sq(s));
    return bb == expected;
}
}  // namespace

TEST_CASE("isolated pawns: no friendly pawn on a neighbour file", "[pawns][isolated]") {
    // White d4 is isolated (no c/e pawns); f3 and g2 defend each other's files.
    Board b("4k3/8/8/8/3P4/5P2/6P1/4K3 w - - 0 1");
    CHECK(only(isolatedPawns(b, Color::WHITE), {"d4"}));
    CHECK(isolatedPawns(b, Color::BLACK).empty());
}

TEST_CASE("doubled pawns: two friendly pawns share a file", "[pawns][doubled]") {
    // White a2 (single) and c2/c4 (doubled).
    Board b("4k3/8/8/8/2P5/8/P1P5/4K3 w - - 0 1");
    CHECK(only(doubledPawns(b, Color::WHITE), {"c2", "c4"}));
    CHECK(doubledPawns(b, Color::BLACK).empty());
}

TEST_CASE("passed pawns: no enemy pawn on the file or its neighbours ahead", "[pawns][passed]") {
    // White e5 with the only black pawn on a7: both are passed.
    Board passed("4k3/p7/8/4P3/8/8/8/4K3 w - - 0 1");
    CHECK(only(passedPawns(passed, Color::WHITE), {"e5"}));
    CHECK(only(passedPawns(passed, Color::BLACK), {"a7"}));

    // Black d7 sits on a neighbour file ahead of e5 — neither pawn is passed now.
    Board blocked("4k3/3p4/8/4P3/8/8/8/4K3 w - - 0 1");
    CHECK(passedPawns(blocked, Color::WHITE).empty());
    CHECK(passedPawns(blocked, Color::BLACK).empty());
}

TEST_CASE("backward pawn: rearmost, stop square held by an enemy pawn", "[pawns][backward]") {
    // White d3 is backward: c4 and e4 have advanced past it, and black's e5 covers d4.
    Board b("4k3/8/8/4p3/2P1P3/3P4/8/4K3 w - - 0 1");
    CHECK(only(backwardPawns(b, Color::WHITE), {"d3"}));
}

TEST_CASE("file state: open and half-open files", "[pawns][files]") {
    // White a2,b2,d4 vs black a7,b7,c5.
    Board b("4k3/pp6/8/2p5/3P4/8/PP6/4K3 w - - 0 1");

    CHECK(isOpenFile(b, File(File::FILE_E)));
    CHECK_FALSE(isOpenFile(b, File(File::FILE_D)));

    CHECK(isHalfOpenFile(b, Color::WHITE, File(File::FILE_C)));  // black-only c-file
    CHECK(isHalfOpenFile(b, Color::BLACK, File(File::FILE_D)));  // white-only d-file
    CHECK_FALSE(isHalfOpenFile(b, Color::WHITE, File(File::FILE_E)));  // open, not half-open

    CHECK(openFileCount(b) == 4);             // e,f,g,h
    CHECK(halfOpenFileCount(b, Color::WHITE) == 1);  // c
    CHECK(halfOpenFileCount(b, Color::BLACK) == 1);  // d
}

TEST_CASE("king shield: intact, tolerant of one push, broken", "[pawns][shield]") {
    Board intact("4k3/8/8/8/8/8/5PPP/6K1 w - - 0 1");
    CHECK(kingShield(intact, Color::WHITE) == 3);

    // g-pawn pushed one square: still shielded (two-rank tolerance).
    Board pushed("6k1/8/8/8/8/6P1/5P1P/6K1 w - - 0 1");
    CHECK(kingShield(pushed, Color::WHITE) == 3);

    // g-file fully open in front of the king: one hole.
    Board broken("6k1/8/8/8/8/8/5P1P/6K1 w - - 0 1");
    CHECK(kingShield(broken, Color::WHITE) == 2);

    Board black_intact("6k1/5ppp/8/8/8/8/8/6K1 w - - 0 1");
    CHECK(kingShield(black_intact, Color::BLACK) == 3);
}
