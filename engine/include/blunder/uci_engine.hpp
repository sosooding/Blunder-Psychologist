#pragma once

#include <string>

#include "blunder/analysis.hpp"

namespace blunder {

struct EngineOptions {
    int threads = 1;        // Threads 1 — multithreaded search is nondeterministic even node-limited
    int hash_mb = 16;       // modest, fixed hash
    int multipv = 3;        // default lines per position
    std::string path;       // stockfish binary; empty => $STOCKFISH_PATH, then "stockfish" on PATH
};

// A long-lived Stockfish process driven over UCI. One process, single-threaded, node-limited
// `go` for cross-machine reproducibility. `ucinewgame` is issued before every analysed position
// so a position's result never depends on what was searched before it (order independence).
//
// Subprocess management is POSIX (fork/exec/pipe): the engine only ever builds and runs inside
// the Linux containers, never on the Windows host.
class UciEngine {
   public:
    explicit UciEngine(EngineOptions opts = {});
    ~UciEngine();

    UciEngine(const UciEngine&) = delete;
    UciEngine& operator=(const UciEngine&) = delete;

    // Analyse one position to `nodes` nodes with `multipv` lines. The returned PvLines are
    // ordered by multipv index (lines[0] == multipv 1 == best).
    PositionEval analyse(const std::string& fen, long nodes, int multipv);

    const EngineOptions& options() const { return opts_; }

   private:
    void start();
    void stop() noexcept;
    void send(const std::string& line);
    std::string readLine();                  // blocks; one line, newline stripped
    void waitForToken(const std::string& token);  // read until a line begins with token
    void setOption(const std::string& name, const std::string& value);

    EngineOptions opts_;
    int in_fd_ = -1;   // write -> child stdin
    int out_fd_ = -1;  // read  <- child stdout
    int pid_ = -1;
    int current_multipv_ = 0;
    std::string read_buf_;
};

// Resolve the stockfish binary: explicit path > $STOCKFISH_PATH > "stockfish" (PATH lookup).
std::string resolveStockfishPath(const std::string& explicit_path);

}  // namespace blunder
