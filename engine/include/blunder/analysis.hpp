#pragma once

#include <string>
#include <vector>

#include "blunder/features.hpp"
#include "blunder/score.hpp"
#include "blunder/severity.hpp"

namespace blunder {

// One line of a multi-PV search result.
struct PvLine {
    Score score;                     // side-to-move perspective
    std::vector<std::string> moves;  // principal variation, UCI long algebraic
};

// Raw analysis of a single position (the result of one engine call, or a terminal verdict).
struct PositionEval {
    std::string fen;
    std::vector<PvLine> lines;  // sorted by multipv index 1..N; lines[0] is the best line
    bool terminal = false;      // checkmate/stalemate — no legal move, engine not invoked

    // Best evaluation for the side to move (multipv 1).
    Score best() const { return lines.empty() ? Score{} : lines.front().score; }
};

// One analyzed ply: the move actually played, evaluated against the engine's best.
struct MoveAnalysis {
    int ply = 0;             // 0-based ply index within the game
    std::string fen;         // position *before* the move
    std::string move_uci;    // move played, UCI long algebraic
    std::string move_san;    // move played, SAN (as it appeared in the PGN)
    bool white_to_move = true;

    int eval_cp = 0;       // White POV, position after the played move
    int best_eval_cp = 0;  // White POV, if the best move had been played
    int delta_cp = 0;      // centipawns lost by the mover (>= 0)

    std::vector<std::string> best_pv;  // engine's best line from the position before the move

    // Phase 2 positional annotation, filled by annotate() from the pre-move position.
    Features features;                   // features from the mover's perspective (incl. archetype)
    int sharpness = 0;                   // MultiPV-3 eval spread (cp): how forcing the position was
    Severity severity = Severity::None;  // inaccuracy / mistake / blunder, scaled by sharpness
};

struct GameAnalysis {
    std::vector<MoveAnalysis> moves;
};

// Canonical, stable text serialization. The determinism test compares this byte-for-byte
// across two independent runs, so the format must be fully ordered and free of any incidental
// state (timings, node counts, pointer values).
std::string serialize(const std::vector<GameAnalysis>& games);

// Fill a move's positional annotation (features, sharpness, severity) from the position it was
// played in (ma.fen) and the engine's evaluation of that position (`before`). Pure board geometry
// plus the pinned thresholds — no engine, no I/O.
void annotate(MoveAnalysis& ma, const PositionEval& before);

}  // namespace blunder
