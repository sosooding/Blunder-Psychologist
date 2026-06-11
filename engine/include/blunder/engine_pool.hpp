#pragma once

#include <string>
#include <vector>

#include "blunder/analysis.hpp"

namespace blunder {

struct AnalyzeParams {
    long nodes = 2'000'000;  // deep-pass default; the cheap pass calls with far fewer
    int multipv = 3;
    int engines = 1;         // size of the process pool; results are pool-size independent
    int hash_mb = 16;
    std::string stockfish_path;  // empty => resolveStockfishPath default
};

// Parse and analyze a batch of PGNs. Every position of every game is evaluated exactly once
// (deduplicated by FEN), then each ply's MoveAnalysis is assembled from consecutive position
// evals: best-move eval = eval of the position before the move; played-move eval = eval of the
// position after it (negated into the mover's perspective). Output ordering is fully
// deterministic and independent of pool size.
std::vector<GameAnalysis> analyzeGames(const std::vector<std::string>& pgns,
                                       const AnalyzeParams& params);

}  // namespace blunder
