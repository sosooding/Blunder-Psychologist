// Features: JSON round-trip (the contract with the Python/DB layer) and an extraction sanity
// check on a known structure.

#include "blunder/features.hpp"
#include "catch_amalgamated.hpp"
#include "chess.hpp"

using namespace blunder;
using chess::Board;
using chess::Color;

TEST_CASE("features JSON round-trips through serialize/parse", "[features][json]") {
    Features f;
    f.isolated_pawns = 1;
    f.doubled_pawns = 2;
    f.backward_pawns = 3;
    f.passed_pawns = 4;
    f.open_files = 2;
    f.half_open_files = 1;
    f.king_shield = 3;
    f.king_zone_attackers = 5;
    f.space = 7;
    f.mobility = 21;
    f.archetype = Archetype::Maroczy;

    const std::string json = toJson(f);
    INFO("json: " << json);
    CHECK(featuresFromJson(json) == f);

    // Surviving an extra leading/trailing whitespace pass (as a DB column might round-trip).
    CHECK(featuresFromJson("  " + json + "\n") == f);
}

TEST_CASE("extractFeatures reads a known IQP structure", "[features]") {
    // White has an isolated d4 pawn; king castled with an intact shield.
    Board b("r2q1rk1/pp3ppp/2n1pn2/8/3P4/2N2N2/PP3PPP/R1BQ1RK1 w - - 0 1");
    const Features f = extractFeatures(b, Color::WHITE);

    CHECK(f.archetype == Archetype::Iqp);
    CHECK(f.isolated_pawns == 1);  // the d4 pawn
    CHECK(f.doubled_pawns == 0);
    CHECK(f.passed_pawns == 0);
    CHECK(f.king_shield == 3);  // f2/g2/h2 in front of the g1 king
    CHECK(f.mobility > 0);

    // Whatever the extractor produced must survive the JSON round-trip too.
    CHECK(featuresFromJson(toJson(f)) == f);
}
