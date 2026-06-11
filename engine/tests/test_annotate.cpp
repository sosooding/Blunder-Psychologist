// annotate() ties the feature layer to a single analyzed move, and serialize() emits the new
// fields deterministically. Both are pure (no engine), so they're exercised here directly.

#include <string>

#include "blunder/analysis.hpp"
#include "catch_amalgamated.hpp"

using namespace blunder;

namespace {
PositionEval evalWith(const char* fen, std::initializer_list<int> line_cps) {
    PositionEval pe;
    pe.fen = fen;
    for (int cp : line_cps) pe.lines.push_back(PvLine{Score::cp(cp), {}});
    return pe;
}
}  // namespace

TEST_CASE("annotate fills features, sharpness and severity from the pre-move position",
          "[annotate]") {
    const char* fen = "r2q1rk1/pp3ppp/2n1pn2/8/3P4/2N2N2/PP3PPP/R1BQ1RK1 w - - 0 1";  // White IQP

    MoveAnalysis ma;
    ma.fen = fen;
    ma.white_to_move = true;
    ma.delta_cp = 300;
    ma.best_eval_cp = 50;  // balanced before the move

    // best 120, third 20 -> sharpness 100 -> scale 1.25 -> blunder bar 312, mistake bar 125.
    annotate(ma, evalWith(fen, {120, 60, 20}));

    CHECK(ma.features.archetype == Archetype::Iqp);
    CHECK(ma.features.isolated_pawns == 1);
    CHECK(ma.sharpness == 100);
    CHECK(ma.severity == Severity::Mistake);  // 300 clears 125 but not the sharpened 312
}

TEST_CASE("annotate suppresses severity in an already-decided position", "[annotate]") {
    const char* fen = "r2q1rk1/pp3ppp/2n1pn2/8/3P4/2N2N2/PP3PPP/R1BQ1RK1 w - - 0 1";
    MoveAnalysis ma;
    ma.fen = fen;
    ma.white_to_move = true;
    ma.delta_cp = 400;
    ma.best_eval_cp = 900;  // already winning by 9 pawns

    annotate(ma, evalWith(fen, {900, 880, 870}));
    CHECK(ma.severity == Severity::None);
}

TEST_CASE("serialize emits the annotation fields", "[annotate][serialize]") {
    const char* fen = "r2q1rk1/pp3ppp/2n1pn2/8/3P4/2N2N2/PP3PPP/R1BQ1RK1 w - - 0 1";
    MoveAnalysis ma;
    ma.ply = 0;
    ma.fen = fen;
    ma.move_uci = "f1e1";
    ma.move_san = "Re1";
    ma.white_to_move = true;
    ma.delta_cp = 300;
    ma.best_eval_cp = 50;
    annotate(ma, evalWith(fen, {120, 60, 20}));

    GameAnalysis ga;
    ga.moves.push_back(ma);
    const std::string out = serialize({ga});

    INFO(out);
    CHECK(out.find("sev mistake") != std::string::npos);
    CHECK(out.find("arch iqp") != std::string::npos);
    CHECK(out.find("feat {\"isolated_pawns\":1") != std::string::npos);
    CHECK(out.find("sharp 100") != std::string::npos);

    // Deterministic: serializing twice is byte-identical.
    CHECK(serialize({ga}) == out);
}
