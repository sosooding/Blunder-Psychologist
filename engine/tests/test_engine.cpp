// RED-first engine suite. These require a real Stockfish binary; when none is found they
// SKIP rather than fail, so the pure unit suite still runs anywhere. The determinism test is
// the headline guarantee of Phase 1: the same input analyzed twice is byte-identical output.

#include <algorithm>
#include <cstddef>
#include <string>
#include <vector>

#include "blunder/analysis.hpp"
#include "blunder/engine_pool.hpp"
#include "blunder/uci_engine.hpp"
#include "catch_amalgamated.hpp"

namespace {

// Scholar's-mate trap: 3...Nf6?? walks into 4.Qxf7#. ply 5 (Black's Nf6) is the blunder.
// Headers included because the PGN parser keys off the tag roster (as every real Lichess
// export has), starting a game only when it sees a `[` tag.
constexpr const char* kScholarsMate =
    "[Event \"Test\"]\n"
    "[Site \"?\"]\n"
    "[White \"W\"]\n"
    "[Black \"B\"]\n"
    "[Result \"1-0\"]\n"
    "\n"
    "1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0\n";

bool engineAvailable() {
    try {
        blunder::UciEngine eng;
        eng.analyse("8/8/8/8/8/8/8/K6k w - - 0 1", 1000, 1);
        return true;
    } catch (...) {
        return false;
    }
}

std::size_t argmaxDelta(const blunder::GameAnalysis& g) {
    std::size_t best = 0;
    for (std::size_t i = 1; i < g.moves.size(); ++i) {
        if (g.moves[i].delta_cp > g.moves[best].delta_cp) best = i;
    }
    return best;
}

}  // namespace

TEST_CASE("determinism: the same PGN analyzed twice is byte-identical", "[engine][determinism]") {
    if (!engineAvailable()) SKIP("stockfish binary not found");

    blunder::AnalyzeParams params;
    params.nodes = 200'000;
    params.multipv = 3;
    params.engines = 1;

    const auto run1 = blunder::analyzeGames({kScholarsMate}, params);
    const auto run2 = blunder::analyzeGames({kScholarsMate}, params);

    CHECK(blunder::serialize(run1) == blunder::serialize(run2));
}

TEST_CASE("determinism holds across pool sizes", "[engine][determinism]") {
    if (!engineAvailable()) SKIP("stockfish binary not found");

    blunder::AnalyzeParams single;
    single.nodes = 150'000;
    single.engines = 1;

    blunder::AnalyzeParams pooled = single;
    pooled.engines = 3;

    CHECK(blunder::serialize(blunder::analyzeGames({kScholarsMate}, single)) ==
          blunder::serialize(blunder::analyzeGames({kScholarsMate}, pooled)));
}

TEST_CASE("sign sanity: the blunder ply is the worst move and flips the eval", "[engine][sign]") {
    if (!engineAvailable()) SKIP("stockfish binary not found");

    blunder::AnalyzeParams params;
    params.nodes = 200'000;
    params.multipv = 3;

    const auto games = blunder::analyzeGames({kScholarsMate}, params);
    REQUIRE(games.size() == 1);
    const auto& g = games[0];
    REQUIRE(g.moves.size() == 7);  // 1.e4 e5 2.Qh5 Nc6 3.Bc4 Nf6 4.Qxf7#

    // ply 5 == Black's Nf6, the move that allows mate.
    const auto& blunder_ply = g.moves[5];
    CHECK(blunder_ply.move_uci == "g8f6");
    CHECK(blunder_ply.white_to_move == false);
    CHECK(blunder_ply.delta_cp >= 5000);   // mate-sized loss
    CHECK(blunder_ply.eval_cp >= 5000);    // after the move White (POV +) is mating

    // It is unambiguously the worst move of the game.
    CHECK(argmaxDelta(g) == 5);

    // A sound opening move loses far less than the blunder.
    CHECK(g.moves[0].move_uci == "e2e4");
    CHECK(g.moves[0].delta_cp < blunder_ply.delta_cp);
    CHECK(g.moves[0].delta_cp < 200);

    // The mating move itself is best — essentially no loss.
    CHECK(g.moves[6].move_uci == "h5f7");
    CHECK(g.moves[6].delta_cp <= 50);
}

TEST_CASE("mate scores: a forced mate-in-1 is detected as a mate", "[engine][mate]") {
    if (!engineAvailable()) SKIP("stockfish binary not found");

    blunder::UciEngine eng;
    // Black king a8, White king b6, White rook h1: 1.Rh8#.
    const auto pe = eng.analyse("k7/8/1K6/8/8/8/8/7R w - - 0 1", 100'000, 1);
    REQUIRE_FALSE(pe.lines.empty());
    CHECK(pe.best().mate == true);
    CHECK(pe.best().mate_in == 1);
    CHECK(pe.best().value == 9999);
    CHECK(pe.lines.front().moves.front() == "h1h8");

    // Re-analysing the same position is identical.
    const auto pe2 = eng.analyse("k7/8/1K6/8/8/8/8/7R w - - 0 1", 100'000, 1);
    CHECK(pe.best() == pe2.best());
}
