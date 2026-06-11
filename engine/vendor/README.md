# Vendored third-party headers

Committed verbatim so the build is hermetic — no network fetch at configure time, which
keeps the engine's reproducibility guarantee from depending on an upstream mirror.

| File | Library | Version | License | Source |
|---|---|---|---|---|
| `chess.hpp` | Disservin **chess-library** | 0.9.4 (commit `57159616358c2d4c09e0d4fb1562ca7f2d36a2fb`) | MIT | https://github.com/Disservin/chess-library |
| `catch_amalgamated.hpp` / `.cpp` | **Catch2** | v3.15.0 | BSL-1.0 | https://github.com/catchorg/Catch2 |

`chess.hpp` provides board representation, FEN, move generation, and the PGN visitor parser.
Catch2 is the C++ test framework (amalgamated single-source distribution).

To refresh a header, re-download from the pinned ref above and update this table. These files
are intentionally **not** linted/formatted by our tooling.
