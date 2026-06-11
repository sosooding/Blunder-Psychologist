#pragma once

#include <algorithm>
#include <string>

// Sharpness and severity: pure arithmetic over evaluations, decided on paper like score.hpp and
// tested at the boundaries. No board, no engine — header-only.
namespace blunder {

enum class Severity { None, Inaccuracy, Mistake, Blunder };

inline std::string severityName(Severity s) {
    switch (s) {
        case Severity::Inaccuracy: return "inaccuracy";
        case Severity::Mistake: return "mistake";
        case Severity::Blunder: return "blunder";
        case Severity::None: break;
    }
    return "none";
}

// How forcing the position is, read from the MultiPV spread between the best line and the
// third-best (both side-to-move POV, so the difference is a clean centipawn gap). A wide spread
// means the best move is nearly the only good one. Clamped to a sane band so a mate score in one
// of the lines can't blow the scale up.
inline constexpr int kSharpnessCap = 800;

inline int sharpness(int best_cp, int third_cp) {
    const int spread = best_cp - third_cp;
    return std::clamp(spread, 0, kSharpnessCap);
}

// Base centipawn thresholds. Below kInaccuracy the move isn't worth flagging.
inline constexpr int kInaccuracyCp = 50;
inline constexpr int kMistakeCp = 100;
inline constexpr int kBlunderCp = 250;

// At or beyond this absolute pre-move eval the game is already decided; a further dip is not a
// meaningful blunder. Keyed on the eval the mover *faced*, not the resulting eval — otherwise a
// clean 0 -> -700 blunder would be silenced by its own consequence.
inline constexpr int kDecidedEvalCp = 600;

// Sharpness at which thresholds are inflated by one base unit (scale = 2.0).
inline constexpr int kSharpnessRefCp = 400;

// Classify how bad a move was.
//   delta_cp          centipawns the mover threw away (>= 0)
//   position_eval_cp  eval of the position the mover faced, White POV (only |.| matters)
//   sharpness_cp      from sharpness(); raises the bar in tactical positions
// In razor-sharp positions the thresholds scale up: a large swing is inherent there and less
// diagnostic of a characteristic weakness.
inline Severity classifySeverity(int delta_cp, int position_eval_cp, int sharpness_cp) {
    if (position_eval_cp > kDecidedEvalCp || position_eval_cp < -kDecidedEvalCp)
        return Severity::None;

    const double scale = 1.0 + double(std::clamp(sharpness_cp, 0, kSharpnessCap)) / kSharpnessRefCp;
    const int blunder = static_cast<int>(kBlunderCp * scale);
    const int mistake = static_cast<int>(kMistakeCp * scale);
    const int inaccuracy = static_cast<int>(kInaccuracyCp * scale);

    if (delta_cp >= blunder) return Severity::Blunder;
    if (delta_cp >= mistake) return Severity::Mistake;
    if (delta_cp >= inaccuracy) return Severity::Inaccuracy;
    return Severity::None;
}

}  // namespace blunder
