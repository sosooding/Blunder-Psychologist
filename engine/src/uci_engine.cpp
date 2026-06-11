#include "blunder/uci_engine.hpp"

#include <fcntl.h>
#include <signal.h>
#include <sys/wait.h>
#include <unistd.h>

#include <algorithm>
#include <cerrno>
#include <cstdlib>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace blunder {

namespace {

// Parse one UCI `info` line, recording its score + principal variation under its multipv
// index. Lines without both a score and a pv (currmove tickers, `info string`, periodic node
// reports) are ignored. The latest line per index wins, so the values left at `bestmove` are
// the completed iteration's exact figures.
void parseInfoLine(const std::string& line, std::vector<std::optional<PvLine>>& by_index) {
    std::istringstream iss(line);
    std::string tok;
    int idx = 1;  // Stockfish omits `multipv` when MultiPV == 1
    bool has_score = false;
    Score score;
    std::vector<std::string> pv;

    while (iss >> tok) {
        if (tok == "multipv") {
            iss >> idx;
        } else if (tok == "score") {
            std::string kind;
            long value = 0;
            iss >> kind >> value;
            score = Score::fromUci(kind, static_cast<int>(value));
            has_score = true;
        } else if (tok == "pv") {
            std::string mv;
            while (iss >> mv) pv.push_back(mv);
            break;
        }
        // Everything else (depth, seldepth, nodes, nps, time, hashfull, tbhits, lowerbound,
        // upperbound, ...) is intentionally ignored.
    }

    if (!has_score || pv.empty()) return;
    if (idx < 1) idx = 1;
    if (static_cast<std::size_t>(idx) > by_index.size()) by_index.resize(idx);
    by_index[static_cast<std::size_t>(idx) - 1] = PvLine{score, std::move(pv)};
}

}  // namespace

std::string resolveStockfishPath(const std::string& explicit_path) {
    if (!explicit_path.empty()) return explicit_path;
    if (const char* env = std::getenv("STOCKFISH_PATH"); env && *env) return env;
    return "stockfish";
}

UciEngine::UciEngine(EngineOptions opts) : opts_(std::move(opts)) { start(); }

UciEngine::~UciEngine() { stop(); }

void UciEngine::start() {
    // A dead engine must surface as EPIPE on write, not as a process-killing signal.
    static const bool ignored_sigpipe = []() {
        ::signal(SIGPIPE, SIG_IGN);
        return true;
    }();
    (void)ignored_sigpipe;

    int to_child[2];    // parent writes [1] -> child reads [0] (stdin)
    int from_child[2];  // child writes [1] -> parent reads [0] (stdout)
    if (::pipe(to_child) != 0 || ::pipe(from_child) != 0) {
        throw std::runtime_error("UciEngine: pipe() failed");
    }
    // The parent-held ends must not leak into a later engine's child (which would hold this
    // engine's pipe open and prevent EOF). Close-on-exec handles that; dup2 in the child clears
    // the flag on the std fds it actually keeps.
    for (int fd : {to_child[0], to_child[1], from_child[0], from_child[1]}) {
        ::fcntl(fd, F_SETFD, FD_CLOEXEC);
    }

    pid_ = ::fork();
    if (pid_ < 0) {
        throw std::runtime_error("UciEngine: fork() failed");
    }

    if (pid_ == 0) {
        // Child: wire the pipe ends to stdin/stdout and exec stockfish.
        ::dup2(to_child[0], STDIN_FILENO);
        ::dup2(from_child[1], STDOUT_FILENO);
        ::close(to_child[0]);
        ::close(to_child[1]);
        ::close(from_child[0]);
        ::close(from_child[1]);
        const std::string path = resolveStockfishPath(opts_.path);
        ::execlp(path.c_str(), path.c_str(), static_cast<char*>(nullptr));
        ::_exit(127);  // exec failed
    }

    // Parent.
    ::close(to_child[0]);
    ::close(from_child[1]);
    in_fd_ = to_child[1];
    out_fd_ = from_child[0];

    send("uci");
    waitForToken("uciok");
    setOption("Threads", std::to_string(opts_.threads));
    setOption("Hash", std::to_string(opts_.hash_mb));
    setOption("MultiPV", std::to_string(opts_.multipv));
    current_multipv_ = opts_.multipv;
    send("isready");
    waitForToken("readyok");
}

void UciEngine::stop() noexcept {
    if (in_fd_ >= 0) {
        const char quit[] = "quit\n";
        ssize_t ignored = ::write(in_fd_, quit, sizeof(quit) - 1);
        (void)ignored;
        ::close(in_fd_);
        in_fd_ = -1;
    }
    if (out_fd_ >= 0) {
        ::close(out_fd_);
        out_fd_ = -1;
    }
    if (pid_ > 0) {
        int status = 0;
        ::waitpid(pid_, &status, 0);
        pid_ = -1;
    }
}

void UciEngine::send(const std::string& line) {
    std::string data = line;
    data.push_back('\n');
    std::size_t off = 0;
    while (off < data.size()) {
        ssize_t n = ::write(in_fd_, data.data() + off, data.size() - off);
        if (n < 0) {
            if (errno == EINTR) continue;
            throw std::runtime_error("UciEngine: write to engine failed");
        }
        off += static_cast<std::size_t>(n);
    }
}

std::string UciEngine::readLine() {
    for (;;) {
        const auto nl = read_buf_.find('\n');
        if (nl != std::string::npos) {
            std::string line = read_buf_.substr(0, nl);
            read_buf_.erase(0, nl + 1);
            if (!line.empty() && line.back() == '\r') line.pop_back();
            return line;
        }
        char buf[4096];
        ssize_t n = ::read(out_fd_, buf, sizeof(buf));
        if (n > 0) {
            read_buf_.append(buf, static_cast<std::size_t>(n));
            continue;
        }
        if (n == 0) {  // EOF
            if (read_buf_.empty()) {
                throw std::runtime_error("UciEngine: engine closed the connection");
            }
            std::string line = read_buf_;
            read_buf_.clear();
            if (!line.empty() && line.back() == '\r') line.pop_back();
            return line;
        }
        if (errno == EINTR) continue;
        throw std::runtime_error("UciEngine: read from engine failed");
    }
}

void UciEngine::waitForToken(const std::string& token) {
    for (;;) {
        const std::string line = readLine();
        if (line.rfind(token, 0) == 0) return;  // line starts with token
    }
}

void UciEngine::setOption(const std::string& name, const std::string& value) {
    send("setoption name " + name + " value " + value);
}

PositionEval UciEngine::analyse(const std::string& fen, long nodes, int multipv) {
    if (multipv != current_multipv_) {
        setOption("MultiPV", std::to_string(multipv));
        current_multipv_ = multipv;
        send("isready");
        waitForToken("readyok");
    }

    // Reset transposition table and search heuristics so this position's result does not
    // depend on whatever was searched before it — the order-independence guarantee.
    send("ucinewgame");
    send("isready");
    waitForToken("readyok");

    send("position fen " + fen);
    send("go nodes " + std::to_string(nodes));

    std::vector<std::optional<PvLine>> by_index(
        static_cast<std::size_t>(std::max(1, multipv)));
    for (;;) {
        const std::string line = readLine();
        if (line.rfind("bestmove", 0) == 0) break;
        if (line.rfind("info", 0) != 0) continue;
        parseInfoLine(line, by_index);
    }

    PositionEval pe;
    pe.fen = fen;
    for (auto& opt : by_index) {
        if (opt) pe.lines.push_back(std::move(*opt));
    }
    return pe;
}

}  // namespace blunder
