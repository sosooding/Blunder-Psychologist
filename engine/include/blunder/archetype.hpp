#pragma once

#include <string>

#include "chess.hpp"

// Pawn-structure archetype classification: ordered, hand-coded bitboard predicates over the
// pawn skeleton, first match wins, with an honest `Unknown` fallback. Rules over a learned
// classifier — every line is explainable and defensible.
namespace blunder {

enum class Archetype {
    Carlsbad,           // QGD Exchange minority-attack skeleton
    Iqp,                // isolated queen's pawn
    HangingPawns,       // abreast c/d pawns on half-open b/e files
    Maroczy,            // c4+e4 bind, no d-pawn
    Hedgehog,           // a6-b6-d6-e6 spine
    Stonewall,          // d5-e6-f5 (or d4-e3-f4) triangle
    FrenchChain,        // d4-e5 vs d5-e6 locked chain
    KidChain,           // d5-e4 vs e5-d6 locked chain
    SymmetricOpen,      // mirror-image skeleton, open centre
    SymmetricClosed,    // mirror-image skeleton, rammed centre
    OppositeCastling,   // kings on opposite wings
    EndgameSimplified,  // queens off, little material left
    Unknown,
};

// Stable snake_case identifier — the value stored in JSON / the DB.
std::string archetypeName(Archetype a);
// Inverse of archetypeName; unrecognized strings map to Unknown.
Archetype archetypeFromName(const std::string& name);

// Classify the pawn structure of a position.
Archetype classify(const chess::Board& b);

}  // namespace blunder
