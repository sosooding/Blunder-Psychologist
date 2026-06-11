// Golden-FEN suite for the pawn-structure classifier. Three hand-picked positions per archetype
// from canonical structures; curating these FENs IS the design work — it forces a precise,
// defensible definition of each structure and an ordering that disambiguates overlaps.

#include <string>
#include <vector>

#include "blunder/archetype.hpp"
#include "catch_amalgamated.hpp"
#include "chess.hpp"

using blunder::Archetype;
using blunder::archetypeName;
using blunder::classify;

namespace {
void expectAll(Archetype expected, const std::vector<std::string>& fens) {
    for (const auto& fen : fens) {
        const Archetype got = classify(chess::Board(fen));
        INFO("FEN: " << fen);
        INFO("expected: " << archetypeName(expected) << "  got: " << archetypeName(got));
        CHECK(got == expected);
    }
}
}  // namespace

TEST_CASE("Carlsbad — QGD Exchange minority-attack skeleton", "[archetype]") {
    expectAll(Archetype::Carlsbad, {
        "2rq1rk1/pp3ppp/2p2n2/3p4/3P4/4PN2/PP3PPP/2RQ1RK1 w - - 0 1",
        "2rq1rk1/5ppp/p1p5/1p1p4/3P4/2N1P3/PP3PPP/2RQ1RK1 w - - 0 1",
        "r2q1rk1/pp3ppp/2n5/2pp4/3P4/4PN2/PP3PPP/R1BQ1RK1 w - - 0 1",
    });
}

TEST_CASE("IQP — isolated queen's pawn", "[archetype]") {
    expectAll(Archetype::Iqp, {
        "r2q1rk1/pp3ppp/2n1pn2/8/3P4/2N2N2/PP3PPP/R1BQ1RK1 w - - 0 1",
        "r2q1rk1/pp3ppp/2n2n2/3p4/8/2N1PN2/PP3PPP/R2Q1RK1 w - - 0 1",
        "2rq1rk1/1b3ppp/p3pn2/8/3P4/P1N1BN2/1P3PPP/2RQ1RK1 w - - 0 1",
    });
}

TEST_CASE("Hanging pawns — abreast c/d on half-open b/e files", "[archetype]") {
    expectAll(Archetype::HangingPawns, {
        "r2q1rk1/pp3ppp/4pn2/8/2PP4/2N2N2/P4PPP/R1BQ1RK1 w - - 0 1",
        "2rq1rk1/pb3ppp/1p2pn2/8/2PP4/P3BN2/5PPP/2RQ1RK1 w - - 0 1",
        "2rq1rk1/p4ppp/4bn2/2pp4/8/P1N1PN2/1P3PPP/2RQ1RK1 w - - 0 1",
    });
}

TEST_CASE("Maroczy bind — c4+e4 clamp, no d-pawn", "[archetype]") {
    expectAll(Archetype::Maroczy, {
        "r2q1rk1/pp3ppp/2np1n2/8/2P1P3/2N2N2/PP3PPP/R1BQ1RK1 w - - 0 1",
        "r1bq1rk1/pp3ppp/3ppn2/8/2P1P3/2N1B3/PP3PPP/R2QKB1R w - - 0 1",
        "r2qk2r/pp3ppp/2n2n2/2p1p3/8/2NP1N2/PP3PPP/R1BQ1RK1 w - - 0 1",
    });
}

TEST_CASE("Hedgehog — a6-b6-d6-e6 spine", "[archetype]") {
    expectAll(Archetype::Hedgehog, {
        "r2qr1k1/3n1ppp/pp1pp3/8/2P1P3/2N2N2/PP3PPP/R2QKB1R w - - 0 1",
        "r1bq1rk1/3n1ppp/pp1pp3/8/3P4/2N1PN2/PP3PPP/R1BQ1RK1 w - - 0 1",
        "2rq1rk1/3nbp1p/pp1ppnp1/8/2P1P3/1PN1BN2/P4PPP/2RQ1RK1 w - - 0 1",
    });
}

TEST_CASE("Stonewall — d5-e6-f5 (or d4-e3-f4) triangle", "[archetype]") {
    expectAll(Archetype::Stonewall, {
        "r1bq1rk1/pp4pp/2p1p3/3p1p2/3P4/2N2N2/PPP2PPP/R1BQ1RK1 w - - 0 1",
        "r1bq1rk1/pp3ppp/2p1p3/3p4/3P1P2/2P1PN2/PP4PP/R1BQ1RK1 w - - 0 1",
        "r2q1rk1/pp3ppp/3bpn2/3p1p2/2PP4/2N1PN2/PP3PPP/R1BQ1RK1 w - - 0 1",
    });
}

TEST_CASE("French chain — d4-e5 vs d5-e6", "[archetype]") {
    expectAll(Archetype::FrenchChain, {
        "r2qk2r/pp3ppp/4p3/2ppP3/3P4/2N2N2/PPP2PPP/R1BQKB1R w - - 0 1",
        "r1bqk2r/pp3ppp/2n1p3/2ppP3/3P4/2P2N2/PP3PPP/RNBQKB1R w - - 0 1",
        "r2qkbnr/pp3ppp/2n1p3/2ppP3/3P2b1/2N2N2/PPP2PPP/R1BQKB1R w - - 0 1",
    });
}

TEST_CASE("KID chain — d5-e4 vs e5-d6", "[archetype]") {
    expectAll(Archetype::KidChain, {
        "r1bq1rk1/ppp2pbp/3p1np1/3Pp3/2P1P3/2N2N2/PP3PPP/R1BQ1RK1 w - - 0 1",
        "r1bq1rk1/ppp1npbp/3p2p1/3Pp3/4P3/2N2N2/PPP2PPP/R1BQ1RK1 w - - 0 1",
        "r1bq1rk1/ppp3bp/3p1np1/3Ppp2/2P1P3/2N2N1P/PP3PP1/R1BQ1RK1 w - - 0 1",
    });
}

TEST_CASE("Opposite-side castling — kings on opposite wings", "[archetype]") {
    expectAll(Archetype::OppositeCastling, {
        "r2q1rk1/pp3ppp/3pp3/8/3PP3/5P2/PP4PP/2KR2Q1 w - - 0 1",
        "r2q1rk1/ppp2ppp/2n2n2/3pp3/3PP3/5N2/PPPQ1PPP/2KR3R w - - 0 1",
        "2kr1b1r/ppp2ppp/2n1bn2/1B1pp3/4P3/2NP1N2/PPP2PPP/R1BQ1RK1 w - - 0 1",
    });
}

TEST_CASE("Symmetric closed — mirror skeleton, rammed centre", "[archetype]") {
    expectAll(Archetype::SymmetricClosed, {
        "r2qk2r/pp3ppp/2p1p3/3p4/3P4/2P1P3/PP3PPP/R2QK2R w - - 0 1",
        "r2qk2r/ppp2ppp/3p4/4p3/4P3/3P4/PPP2PPP/R2QK2R w - - 0 1",
        "r2qk2r/pp2pppp/8/2pp4/2PP4/8/PP2PPPP/R2QK2R w - - 0 1",
    });
}

TEST_CASE("Symmetric open — mirror skeleton, open centre", "[archetype]") {
    expectAll(Archetype::SymmetricOpen, {
        "r2qk2r/pppp1ppp/8/8/8/8/PPPP1PPP/R2QK2R w - - 0 1",
        "r2qk2r/ppp2ppp/8/8/8/8/PPP2PPP/R2QK2R w - - 0 1",
        "r2qk2r/pp3ppp/2pp4/8/8/2PP4/PP3PPP/R2QK2R w - - 0 1",
    });
}

TEST_CASE("Endgame simplified — queens off, little left", "[archetype]") {
    expectAll(Archetype::EndgameSimplified, {
        "8/5k2/8/4p3/4P3/8/3K4/8 w - - 0 1",
        "8/5k2/6p1/8/8/1R6/r4PK1/8 w - - 0 1",
        "8/4k3/4b3/8/2N5/8/4K3/8 w - - 0 1",
    });
}

TEST_CASE("Unknown — unstructured middlegames match nothing", "[archetype]") {
    expectAll(Archetype::Unknown, {
        "r1bqk2r/pp2bppp/2n1pn2/8/3NP3/2N1B3/PPP2PPP/R2QKB1R w KQkq - 0 1",
        "r1bqkb1r/1p3ppp/p1np1n2/4p3/4P3/2N2N2/PPPP1PPP/R1BQKB1R w KQkq - 0 1",
    });
}
