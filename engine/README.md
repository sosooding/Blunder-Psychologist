# engine/ — C++ analysis core

Placeholder in Phase 0 (a trivial CMake target so CI builds something).

**Phase 1** fills this in:
- a long-lived Stockfish UCI driver (`Threads 1`, node-limited `go nodes`, MultiPV 3),
- deterministic eval-delta computation (side-to-move normalized, mate mapping),
- bitboard feature extraction + the pawn-archetype classifier (Phase 2),
- a pybind11 module `blunder_engine` exposing `analyze_games(...)` with the GIL released.

Build the placeholder:

```bash
cmake -S engine -B engine/build
cmake --build engine/build
```
