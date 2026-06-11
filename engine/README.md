# engine/ — C++ analysis core

Deterministic, batch Stockfish analysis, exposed to Python as the `blunder_engine` module.

## What's here (Phase 1)

- **`UciEngine`** (`src/uci_engine.cpp`) — a long-lived Stockfish process driven over UCI via
  POSIX pipes. `Threads 1` (single-threaded search is the only deterministic mode), node-limited
  `go nodes N`, `MultiPV 3`, and `ucinewgame` before every position so a result never depends on
  what was searched before it.
- **Score semantics** (`include/blunder/score.hpp`) — pure, header-only delta arithmetic:
  side-to-move normalization, mate mapping `±(10000 − distance)`, White-perspective at the API
  boundary, and `delta = best − played`. The sign conventions are pinned by hand-computed unit
  tests (`tests/test_score.cpp`) written before the implementation.
- **`analyzeGames` + engine pool** (`src/engine_pool.cpp`) — parses PGNs (vendored chess-library
  visitor), evaluates each unique position once across a pool of engine processes, and assembles
  per-ply `MoveAnalysis` from consecutive position evals. Output is byte-for-byte deterministic
  and independent of pool size.
- **pybind11 module** (`bindings/module.cpp`) — `analyze_games(pgns, nodes, multipv, engines,
  stockfish_path)` with the GIL released, plus `serialize(...)`.

Features, the pawn-archetype classifier, sharpness, and severity arrive in **Phase 2**.

## Building

The engine builds inside the Linux containers (the UCI driver uses POSIX process/pipe APIs);
there is no Windows-native toolchain. A Stockfish binary must be reachable at runtime via
`$STOCKFISH_PATH` or on `PATH`.

C++ library + Catch2 tests:

```bash
cmake -S engine -B engine/build -DCMAKE_BUILD_TYPE=Release
cmake --build engine/build -j
ctest --test-dir engine/build --output-on-failure
```

Python wheel (scikit-build-core builds the pybind11 module):

```bash
pip install ./engine
python engine/tests/smoke_wheel.py   # build smoke test (needs Stockfish)
```

The pure score suite runs anywhere; the engine-dependent tests SKIP when no Stockfish is found.

## Determinism

Reproducibility rests on three choices: `Threads 1`, a fixed node budget, and a pinned official
Stockfish binary with its NNUE net embedded (the worker image and CI both install `sf_18`'s
generic `x86-64` build). Same binary + same nodes + single thread ⇒ identical evaluations.

Third-party headers (`chess.hpp`, Catch2) are vendored under `vendor/` — see `vendor/README.md`.
