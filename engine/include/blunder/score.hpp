#pragma once

#include <algorithm>
#include <string_view>

// Pure evaluation arithmetic — no engine, no I/O. This header is where the delta sign
// conventions are decided "on paper": the unit tests in tests/test_score.cpp hand-compute
// every transformation here, so the semantics are pinned before any Stockfish call exists.
namespace blunder {

// Internal score scale, in centipawn-equivalent units, from the side-to-move's perspective
// (positive = good for the side to move). Mate scores are mapped into a band near
// +/-kMateScore so a forced mate always dominates any real centipawn evaluation.
inline constexpr int kMateScore = 10000;

// |score| at or above this is treated as a mate score. Real cp evals are clamped well below
// it (see kMaxCp), so the two bands never collide.
inline constexpr int kMateThreshold = 9000;

// Hard clamp on cp evaluations: a pathological reading can never masquerade as a mate.
inline constexpr int kMaxCp = 8000;

// Map a UCI `mate N` distance to the internal scale: sign(n) * (kMateScore - |n|).
// n > 0: the side to move delivers mate in N; n < 0: the side to move is mated in N.
// Shorter mates map to a larger magnitude, so faster mates compare as "better".
constexpr int mateValue(int mate_in) {
    const int dist = mate_in < 0 ? -mate_in : mate_in;
    const int magnitude = kMateScore - dist;
    return mate_in < 0 ? -magnitude : magnitude;
}

constexpr bool isMateScore(int value) {
    return value >= kMateThreshold || value <= -kMateThreshold;
}

// A single evaluation, always from the side-to-move's perspective.
struct Score {
    int value = 0;      // internal scale: clamped cp, or mate-mapped
    bool mate = false;  // came from a UCI `mate` score
    int mate_in = 0;    // signed UCI mate distance; 0 when !mate

    static constexpr Score cp(int centipawns) {
        return Score{std::clamp(centipawns, -kMaxCp, kMaxCp), false, 0};
    }

    static constexpr Score mateIn(int n) { return Score{mateValue(n), true, n}; }

    // Build from a parsed UCI score token: kind is "cp" or "mate".
    static Score fromUci(std::string_view kind, int n) {
        return kind == "mate" ? mateIn(n) : cp(n);
    }

    constexpr bool operator==(const Score& other) const {
        return value == other.value && mate == other.mate && mate_in == other.mate_in;
    }
};

// View a side-to-move score from the opponent's side. Used to pull the evaluation of the
// position *after* a move (reported from the opponent's perspective) back into the mover's.
constexpr Score negate(Score s) {
    return Score{-s.value, s.mate, -s.mate_in};
}

// Convert a side-to-move score to White's perspective (+ = good for White). This is the
// normalization applied at the API boundary so stored evals read like a chess GUI's.
constexpr int whitePov(Score stm, bool white_to_move) {
    return white_to_move ? stm.value : -stm.value;
}

// Centipawns the mover threw away on this move: best-move eval minus played-move eval, both
// in the mover's perspective. `best` is the evaluation of the position the mover faces
// (mover POV). `after_played` is the evaluation of the resulting position, reported from the
// opponent's perspective (that position's side to move), so it is negated into the mover's.
// Clamped at 0: the best move is by definition no worse than the one played, and independent
// searches of the two positions can otherwise produce tiny negative noise.
constexpr int deltaCp(Score best, Score after_played) {
    const int played_mover_pov = negate(after_played).value;
    const int d = best.value - played_mover_pov;
    return d < 0 ? 0 : d;
}

}  // namespace blunder
