#include <sstream>
#include <string>

#include "blunder/analysis.hpp"

namespace blunder {

std::string serialize(const std::vector<GameAnalysis>& games) {
    std::ostringstream os;
    for (std::size_t gi = 0; gi < games.size(); ++gi) {
        os << "game " << gi << "\n";
        for (const auto& m : games[gi].moves) {
            os << "ply " << m.ply << " stm " << (m.white_to_move ? 'w' : 'b') << " move "
               << m.move_uci << " san " << m.move_san << " eval " << m.eval_cp << " best "
               << m.best_eval_cp << " delta " << m.delta_cp << " pv";
            for (const auto& mv : m.best_pv) os << ' ' << mv;
            os << "\n";
        }
    }
    return os.str();
}

}  // namespace blunder
