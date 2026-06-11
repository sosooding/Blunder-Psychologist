#include "blunder/engine_pool.hpp"

#include <algorithm>
#include <atomic>
#include <mutex>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

#include "blunder/uci_engine.hpp"
#include "chess.hpp"

namespace blunder {

namespace {

struct Ply {
    std::string move_uci;
    std::string move_san;
    bool white_to_move = true;
};

struct ParsedGame {
    std::vector<std::string> fens;  // size == plies.size() + 1 (positions P0..Pn)
    std::vector<Ply> plies;
};

bool isResultToken(std::string_view s) {
    return s == "1-0" || s == "0-1" || s == "1/2-1/2" || s == "*";
}

// Replays a PGN move-by-move, recording the FEN before each ply and the move in UCI + SAN.
// A malformed or illegal SAN truncates that game rather than aborting the batch.
class GameCollector : public chess::pgn::Visitor {
   public:
    std::vector<ParsedGame> games;

    void startPgn() override {
        start_fen_.clear();
        variant_unsupported_ = false;
        broken_ = false;
        started_ = false;
        cur_ = ParsedGame{};
    }

    void header(std::string_view key, std::string_view value) override {
        if (key == "FEN") {
            start_fen_ = std::string(value);
        } else if (key == "Variant") {
            if (!value.empty() && value != "Standard" && value != "From Position") {
                variant_unsupported_ = true;
            }
        }
    }

    void startMoves() override {
        board_.setFen(start_fen_.empty() ? chess::constants::STARTPOS : start_fen_);
        cur_.fens.clear();
        cur_.plies.clear();
        cur_.fens.push_back(board_.getFen());
        started_ = true;
    }

    void move(std::string_view m, std::string_view /*comment*/) override {
        if (broken_ || variant_unsupported_) return;
        if (isResultToken(m)) return;

        chess::Move mv = chess::Move::NO_MOVE;
        try {
            mv = chess::uci::parseSan(board_, m);
        } catch (...) {
            broken_ = true;
            return;
        }
        if (mv == chess::Move::NO_MOVE) {
            broken_ = true;
            return;
        }

        Ply p;
        p.move_uci = chess::uci::moveToUci(mv);
        p.move_san = std::string(m);
        p.white_to_move = (board_.sideToMove() == chess::Color::WHITE);
        board_.makeMove(mv);

        cur_.plies.push_back(std::move(p));
        cur_.fens.push_back(board_.getFen());
    }

    void endPgn() override {
        if (started_ && !variant_unsupported_ && !cur_.plies.empty()) {
            games.push_back(std::move(cur_));
        }
    }

   private:
    chess::Board board_;
    ParsedGame cur_;
    std::string start_fen_;
    bool variant_unsupported_ = false;
    bool broken_ = false;
    bool started_ = false;
};

std::vector<ParsedGame> parsePgns(const std::vector<std::string>& pgns) {
    std::vector<ParsedGame> parsed;
    for (const auto& pgn : pgns) {
        std::istringstream stream(pgn);
        GameCollector collector;
        chess::pgn::StreamParser<> parser(stream);
        parser.readGames(collector);
        for (auto& g : collector.games) parsed.push_back(std::move(g));
    }
    return parsed;
}

// A position with no legal move is terminal: checkmate (side to move is lost) or stalemate
// (draw). These are resolved without the engine.
std::optional<PositionEval> terminalEval(const std::string& fen) {
    chess::Board board(fen);
    chess::Movelist moves;
    chess::movegen::legalmoves(moves, board);
    if (!moves.empty()) return std::nullopt;

    PositionEval pe;
    pe.fen = fen;
    pe.terminal = true;
    const Score s = board.inCheck() ? Score{-kMateScore, true, 0}  // mated
                                    : Score::cp(0);                 // stalemate
    pe.lines.push_back(PvLine{s, {}});
    return pe;
}

// Evaluate the given worklist of FEN indices across a pool of engine processes. Each position
// is independent (ucinewgame resets state), so results are identical regardless of pool size.
void runEnginePool(const std::vector<std::string>& fens, const std::vector<int>& work,
                   std::vector<PositionEval>& evals, const AnalyzeParams& params) {
    if (work.empty()) return;

    int n_engines = std::clamp<int>(params.engines, 1, static_cast<int>(work.size()));

    std::atomic<std::size_t> cursor{0};
    std::atomic<bool> failed{false};
    std::mutex err_mutex;
    std::string first_error;

    auto worker = [&]() {
        try {
            EngineOptions opt;
            opt.threads = 1;
            opt.hash_mb = params.hash_mb;
            opt.multipv = params.multipv;
            opt.path = params.stockfish_path;
            UciEngine engine(opt);

            for (;;) {
                const std::size_t k = cursor.fetch_add(1);
                if (k >= work.size() || failed.load()) break;
                const int idx = work[k];
                evals[idx] = engine.analyse(fens[idx], params.nodes, params.multipv);
            }
        } catch (const std::exception& e) {
            std::lock_guard<std::mutex> lock(err_mutex);
            if (!failed.exchange(true)) first_error = e.what();
        }
    };

    if (n_engines == 1) {
        worker();
    } else {
        std::vector<std::thread> threads;
        threads.reserve(static_cast<std::size_t>(n_engines));
        for (int i = 0; i < n_engines; ++i) threads.emplace_back(worker);
        for (auto& t : threads) t.join();
    }

    if (failed.load()) throw std::runtime_error("engine pool failed: " + first_error);
}

}  // namespace

std::vector<GameAnalysis> analyzeGames(const std::vector<std::string>& pgns,
                                       const AnalyzeParams& params) {
    const std::vector<ParsedGame> parsed = parsePgns(pgns);

    // Deduplicate positions by FEN — repeated positions across games are analyzed once.
    std::unordered_map<std::string, int> fen_index;
    std::vector<std::string> fens;
    for (const auto& g : parsed) {
        for (const auto& f : g.fens) {
            if (fen_index.emplace(f, static_cast<int>(fens.size())).second) fens.push_back(f);
        }
    }

    std::vector<PositionEval> evals(fens.size());
    std::vector<int> engine_work;
    engine_work.reserve(fens.size());
    for (int i = 0; i < static_cast<int>(fens.size()); ++i) {
        if (auto term = terminalEval(fens[i])) {
            evals[i] = std::move(*term);
        } else {
            engine_work.push_back(i);
        }
    }

    runEnginePool(fens, engine_work, evals, params);

    std::vector<GameAnalysis> out;
    out.reserve(parsed.size());
    for (const auto& g : parsed) {
        GameAnalysis ga;
        ga.moves.reserve(g.plies.size());
        for (std::size_t i = 0; i < g.plies.size(); ++i) {
            const PositionEval& before = evals[fen_index[g.fens[i]]];
            const PositionEval& after = evals[fen_index[g.fens[i + 1]]];
            const Score best = before.best();        // mover's perspective
            const Score after_best = after.best();   // opponent's perspective (resulting pos)
            const bool white = g.plies[i].white_to_move;

            MoveAnalysis ma;
            ma.ply = static_cast<int>(i);
            ma.fen = g.fens[i];
            ma.move_uci = g.plies[i].move_uci;
            ma.move_san = g.plies[i].move_san;
            ma.white_to_move = white;
            ma.best_eval_cp = whitePov(best, white);
            ma.eval_cp = whitePov(negate(after_best), white);
            ma.delta_cp = deltaCp(best, after_best);
            if (!before.lines.empty()) ma.best_pv = before.lines.front().moves;
            annotate(ma, before);  // features, archetype, sharpness, severity
            ga.moves.push_back(std::move(ma));
        }
        out.push_back(std::move(ga));
    }
    return out;
}

}  // namespace blunder
