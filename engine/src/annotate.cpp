#include <cstddef>

#include "blunder/analysis.hpp"
#include "blunder/features.hpp"
#include "blunder/severity.hpp"
#include "chess.hpp"

namespace blunder {

void annotate(MoveAnalysis& ma, const PositionEval& before) {
    const chess::Board board(ma.fen);
    const chess::Color mover = ma.white_to_move ? chess::Color::WHITE : chess::Color::BLACK;
    ma.features = extractFeatures(board, mover);

    // Sharpness from the MultiPV spread of the position the mover faced: best line vs the
    // third-best (or the last available line when fewer than three were searched). Both scores
    // are side-to-move POV, so the gap is a clean centipawn spread.
    const int best_cp = before.best().value;
    int third_cp = best_cp;
    if (before.lines.size() >= 3) {
        third_cp = before.lines[2].score.value;
    } else if (before.lines.size() == 2) {
        third_cp = before.lines[1].score.value;
    }
    ma.sharpness = sharpness(best_cp, third_cp);

    // Severity keys on the eval the mover faced (best_eval_cp) so a clean blunder from a balanced
    // position is never silenced by its own consequence.
    ma.severity = classifySeverity(ma.delta_cp, ma.best_eval_cp, ma.sharpness);
}

}  // namespace blunder
