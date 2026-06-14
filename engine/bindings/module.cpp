#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <string>
#include <vector>

#include "blunder/analysis.hpp"
#include "blunder/engine_pool.hpp"
#include "blunder/features.hpp"
#include "chess.hpp"

namespace py = pybind11;
using namespace blunder;

PYBIND11_MODULE(blunder_engine, m) {
    m.doc() = "Blunder Psychologist — native chess analysis engine (Stockfish/UCI, pybind11).";

    py::class_<MoveAnalysis>(m, "MoveAnalysis")
        .def_readonly("ply", &MoveAnalysis::ply)
        .def_readonly("fen", &MoveAnalysis::fen)
        .def_readonly("move_uci", &MoveAnalysis::move_uci)
        .def_readonly("move_san", &MoveAnalysis::move_san)
        .def_readonly("white_to_move", &MoveAnalysis::white_to_move)
        .def_readonly("eval_cp", &MoveAnalysis::eval_cp)
        .def_readonly("best_eval_cp", &MoveAnalysis::best_eval_cp)
        .def_readonly("delta_cp", &MoveAnalysis::delta_cp)
        .def_readonly("best_pv", &MoveAnalysis::best_pv)
        .def_readonly("sharpness", &MoveAnalysis::sharpness)
        .def_property_readonly(
            "severity", [](const MoveAnalysis& a) { return severityName(a.severity); })
        .def_property_readonly(
            "archetype", [](const MoveAnalysis& a) { return archetypeName(a.features.archetype); })
        .def_property_readonly("features",
                               [](const MoveAnalysis& a) { return toJson(a.features); })
        .def("__repr__", [](const MoveAnalysis& a) {
            return "<MoveAnalysis ply=" + std::to_string(a.ply) + " move=" + a.move_uci +
                   " delta_cp=" + std::to_string(a.delta_cp) + ">";
        });

    py::class_<GameAnalysis>(m, "GameAnalysis").def_readonly("moves", &GameAnalysis::moves);

    m.def(
        "analyze_games",
        [](const std::vector<std::string>& pgns, long nodes, int multipv, int engines,
           const std::string& stockfish_path) {
            AnalyzeParams params;
            params.nodes = nodes;
            params.multipv = multipv;
            params.engines = engines;
            params.stockfish_path = stockfish_path;

            std::vector<GameAnalysis> result;
            {
                // The engine work is pure subprocess I/O and native compute — hold no GIL.
                py::gil_scoped_release release;
                result = analyzeGames(pgns, params);
            }
            return result;
        },
        py::arg("pgns"), py::arg("nodes") = 2'000'000, py::arg("multipv") = 3,
        py::arg("engines") = 1, py::arg("stockfish_path") = std::string{},
        "Analyze a batch of PGNs and return a list of GameAnalysis (one per game).");

    m.def("serialize", &serialize, py::arg("games"),
          "Canonical, deterministic text serialization of a list of GameAnalysis.");

    m.def(
        "extract_features",
        [](const std::string& fen, bool white_perspective) {
            const chess::Board board(fen);
            const chess::Color persp =
                white_perspective ? chess::Color::WHITE : chess::Color::BLACK;
            return toJson(extractFeatures(board, persp));
        },
        py::arg("fen"), py::arg("white_perspective"),
        "Extract the positional feature vector for `fen` from the given side's perspective "
        "(true = White), returned as the same compact JSON used in move_analyses.features. "
        "Stockfish-free: pure board geometry over the vendored chess library.");
}
