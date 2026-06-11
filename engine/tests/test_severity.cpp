// Boundary-value tests for sharpness and the severity classifier. The thresholds and the
// sharpness scaling are pinned here so the labels can't drift silently.

#include "blunder/severity.hpp"
#include "catch_amalgamated.hpp"

using namespace blunder;

TEST_CASE("sharpness is the clamped best-vs-third spread", "[severity][sharpness]") {
    CHECK(sharpness(120, 20) == 100);
    CHECK(sharpness(50, 50) == 0);
    CHECK(sharpness(10, 80) == 0);                 // negative spread floors at 0
    CHECK(sharpness(9999, -50) == kSharpnessCap);  // a mate line can't blow up the scale
}

TEST_CASE("severity thresholds in a calm position (sharpness 0)", "[severity]") {
    const int eval = 0, sharp = 0;
    CHECK(classifySeverity(49, eval, sharp) == Severity::None);
    CHECK(classifySeverity(50, eval, sharp) == Severity::Inaccuracy);
    CHECK(classifySeverity(99, eval, sharp) == Severity::Inaccuracy);
    CHECK(classifySeverity(100, eval, sharp) == Severity::Mistake);
    CHECK(classifySeverity(249, eval, sharp) == Severity::Mistake);
    CHECK(classifySeverity(250, eval, sharp) == Severity::Blunder);
    CHECK(classifySeverity(900, eval, sharp) == Severity::Blunder);
}

TEST_CASE("decided positions suppress the flag, keyed on the pre-move eval", "[severity]") {
    // Already winning by more than 6 pawns before the move: a dip doesn't matter.
    CHECK(classifySeverity(500, 601, 0) == Severity::None);
    // Already lost: same.
    CHECK(classifySeverity(500, -601, 0) == Severity::None);
    // Exactly at the boundary is NOT suppressed.
    CHECK(classifySeverity(300, 600, 0) == Severity::Blunder);
    // A clean blunder from a balanced position is still flagged (suppression uses pre-move eval,
    // not the resulting one).
    CHECK(classifySeverity(700, 0, 0) == Severity::Blunder);
}

TEST_CASE("sharper positions raise the bar", "[severity][sharpness]") {
    // sharpness 400 => scale 2.0 => blunder threshold 500, mistake 200.
    CHECK(classifySeverity(250, 0, 0) == Severity::Blunder);    // calm: a blunder
    CHECK(classifySeverity(250, 0, 400) == Severity::Mistake);  // sharp: only a mistake
    CHECK(classifySeverity(199, 0, 400) == Severity::Inaccuracy);
    CHECK(classifySeverity(500, 0, 400) == Severity::Blunder);
}
