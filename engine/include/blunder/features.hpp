#pragma once

#include <string>

#include "blunder/archetype.hpp"
#include "chess.hpp"

// Positional feature vector for one position, computed from the perspective of the side whose
// play is being profiled. Pure board geometry plus the archetype label; serialized to JSON for
// the move_analyses.features column downstream.
namespace blunder {

struct Features {
    // Pawn structure (perspective side).
    int isolated_pawns = 0;
    int doubled_pawns = 0;
    int backward_pawns = 0;
    int passed_pawns = 0;

    // Files.
    int open_files = 0;       // open for both colours
    int half_open_files = 0;  // half-open for the perspective side

    // King safety (perspective king).
    int king_shield = 0;        // 0..3 intact shield files in front of the king
    int king_zone_attackers = 0;  // distinct enemy pieces bearing on the king's zone

    // Space & activity (perspective side).
    int space = 0;     // squares in the enemy half controlled by perspective pawns
    int mobility = 0;  // squares the perspective's minor/major pieces attack (own pieces excluded)

    Archetype archetype = Archetype::Unknown;

    bool operator==(const Features&) const = default;
};

// Extract features for `perspective` (the side whose move we are judging).
Features extractFeatures(const chess::Board& b, chess::Color perspective);

// Compact, deterministic JSON object; archetype is its string id.
std::string toJson(const Features& f);
// Inverse of toJson — parses our own schema (round-trip), tolerant of surrounding whitespace.
Features featuresFromJson(const std::string& json);

}  // namespace blunder
