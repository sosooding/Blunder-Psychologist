# Blunder Psychologist — Execution Plan

Eight phases. Every phase ends runnable, each has an exit test and an interview artifact.

**Methodology:** strict TDD (red → green → refactor) on the deterministic core — engine interop, feature extraction, motif detection — where steps are labeled **RED** (write the failing test first) and **GREEN** (implement until it passes). The LLM layer (Psychologist, Plan Explainer) is eval-driven instead: schema-validation tests plus the plan-consistency check in v1, the predictive-validity harness in v2. Scaffolding and UI get smoke tests, not TDD.
Stack: C++ engine core (Stockfish/UCI, pybind11) · Python agents (LangGraph, LangChain, FAISS, MCP) · TypeScript/React (Engine Room theme) · PostgreSQL · Docker. All free: Gemini Flash / Ollama, local bge-small embeddings.

---

## Phase 0 — Scaffold

**Objective:** a green `docker compose up` with a working job queue, before any chess logic exists.

1. Init monorepo: `engine/` `core/` `web/` `docker/`, `.gitignore`, LICENSE (MIT), README stub with the one-paragraph pitch.
2. Write `docker/worker.Dockerfile`: Python 3.12 base, install Stockfish (official binary release for the target arch), build deps for the future C++ module.
3. Write `docker/api.Dockerfile` (FastAPI + uvicorn) and `web` dev container (node 20 + Vite).
4. `compose.yaml`: postgres:16 with volume + healthcheck, api, worker, web; one `.env` for config (`LLM_PROVIDER`, `DATABASE_URL`, `LICHESS_TOKEN`).
5. Set up Alembic; first migration creates `users`, `games`, `move_analyses`, `blunders`, `profiles`, `jobs` (schema as designed — `features` JSONB, `profiles` append-only versioned).
6. Implement the queue MVP in `core/queue.py`: `enqueue(type, payload, priority)`, worker poll loop claiming with `SELECT … FOR UPDATE SKIP LOCKED`, `attempts` + dead-letter status.
7. Register a `hello` job type; worker executes and marks done.
8. GitHub Actions: ruff + pytest, compose build, placeholder C++ build job.

**Exit test:** `docker compose up` green; enqueue `hello` → worker log shows completion; CI green on push.
**Interview artifact:** "Postgres-backed priority queue with SKIP LOCKED — no Redis, no Celery, and I can explain why."

---

## Phase 1 — Engine Core (C++)

**Objective:** deterministic, batch Stockfish analysis callable from Python — tests written before the engine code exists.

1. `engine/` CMake skeleton; vendor a header-only chess library (e.g. Disservin's chess-library) for board representation; Catch2 for tests.
2. **RED:** write the sign-convention tests first — 5 hand-computed positions with expected eval-deltas, including at least one mate-score case and one Black-to-move case. They fail; nothing exists yet. Hand-computing these forces the delta semantics to be decided on paper before code.
3. **RED:** write the determinism test: analyze the same PGN twice → assert byte-identical output.
4. **GREEN:** implement `UciEngine`: spawn Stockfish, `uci`/`isready` handshake, options. **`Threads 1` per engine** — multithreaded Stockfish is nondeterministic even node-limited; scale with more processes, not threads. `MultiPV 3`, modest `Hash`.
5. **GREEN:** implement `analyse(fen, nodes)` — `position fen …` + `go nodes N`, parse `info` lines into `{multipv, score(cp|mate), pv[]}` — and the delta computation, iterating until the sign-convention tests pass. Mate mapping: `mate N` → `±(10000 − ply_distance)`; normalize to side-to-move, then White perspective at the API boundary.
6. **GREEN:** `EnginePool` (N engines, futures API) + batch game analysis; determinism test goes green and into CI.
7. **REFACTOR:** clean the public interface, then wrap it in the pybind11 module `blunder_engine`: `analyze_games(list[pgn], nodes, multipv)`, releasing the GIL; build the wheel in CI, import in the worker image.

**Exit test:** the Phase 1 suite (sign conventions + determinism) green in CI; Python batch-analyzes a PGN reproducibly.
**Interview artifact:** the determinism test + the Threads=1 story.

---

## Phase 2 — Features & Archetypes

**Objective:** every analyzed position carries positional features and a pawn-structure archetype — the golden-FEN suite exists before the classifier does.

1. **RED:** build the golden-FEN suite first: 3–5 hand-picked FENs per archetype from known games (Carlsbad, IQP, hanging pawns, Maróczy bind, Hedgehog, Stonewall, French chain, KID chain, symmetric open, symmetric closed, opposite-castling race, endgame-simplified), each asserting its expected classification. Curating these *is* the design work — it forces precise definitions of each structure.
2. **RED:** per-predicate fixture tests for the bitboard helpers: positions with known isolated/backward/doubled/passed pawns, open files, broken pawn shields.
3. **GREEN:** implement the bitboard helpers until the predicate tests pass.
4. **GREEN:** implement the classifier as ordered predicates until the golden suite is green. `unknown` is a valid output — never force-fit.
5. Define the `Features` struct (files, pawn flags, shield integrity, king-zone attackers, space, mobility) + JSON serialization, with a round-trip test.
6. Sharpness metric (MultiPV-3 eval spread) and severity classifier (inaccuracy 50–100cp / mistake 100–250cp / blunder 250cp+, scaled by sharpness, suppressed when |eval| > 600cp) — boundary-value tests for both.
7. **REFACTOR:** extend the pybind11 output to include features, archetype, sharpness, severity.

**Exit test:** golden-FEN suite + predicate suite green in CI.
**Interview artifact:** "Hand-coded bitboard predicates over a learned classifier — explainable and debuggable, and I can defend every line."

---

## Phase 3 — Ingestion & the Two-Pass Funnel

**Objective:** type a username → 300 games backfilled → blunder candidates in Postgres, at ~10x less compute than naive analysis.

1. Register a Lichess API token; implement the client with httpx: `GET /api/games/user/{u}?clocks=true&evals=true&perfType=rapid,classical&rated=true`, NDJSON streaming, exponential backoff on 429.
2. Implement the backfill sampler: configurable strategy (`recent | random | stratified`), default stratified (~300 recent + ~100 older), cap 400 games.
3. Parse games with python-chess; extract per-move clocks and embedded Lichess evals where present; insert `games` rows with `analysis_status`.
4. Book-exit detection: opening-explorer client querying each position until games-count drops below threshold → `games.book_exit_ply`; cache explorer responses by FEN (positions repeat heavily across games); flat move-10 fallback if the API is down. Blunder-opportunity counting starts after book exit.
5. Cheap pass — **profiled user's moves only**, post-book: where Lichess evals exist, threshold deltas directly; where absent, run the engine at ~100k nodes. Output: candidate plies per game.
6. Deep pass job type: candidates → full Phase 1+2 pipeline (2M nodes, MultiPV 3, features) → `move_analyses` + `blunders` rows (user-side only; opponent positions evaluated only as delta inputs, never stored as blunders).
7. Priority lanes: on-demand single game (by Lichess URL or PGN paste) = priority 0; backfill chunks (25 games/job) = priority 10. Workers always drain priority 0 first.
8. Incremental sync (`last_synced_at`); progress tracking in `jobs.payload`; FastAPI endpoints: `POST /users/{u}/backfill`, `POST /games/analyze`, `GET /users/{u}/status`.
9. Measure and log the funnel ratio (positions deep-analyzed ÷ total positions) — you want the real number for the README.

**Exit test:** fresh username → backfill completes unattended → candidates and deep analyses in DB; on-demand game jumps the backfill queue.
**Interview artifact:** the measured 10x funnel ratio.

---
## Phase 4 — Annotation & RAG

**Objective:** every blunder gets a grounded annotation and is retrievable by similarity — `find_similar_blunders(fen)` works.

1. **RED (tactical):** sample labeled fixtures from the Lichess puzzle database — thousands of positions per theme (fork, pin, hangingPiece, backRankMate, …) mapped onto the tactical tag vocabulary; write failing detector tests asserting precision/recall floors per motif, not just pass/fail.
2. **GREEN (tactical):** implement the tactical detectors over engine output + bitboards until the benchmarks pass.
3. **RED (positional):** mine the positional fixture pool from the Lichess open database — eval swings in quiet positions (low sharpness) where no tactical detector fires; hand-verify ~100 as the golden subset; write failing tests for the positional detectors (structure damage, tension release, file concession, king-shield weakening, bad trade, outpost concession, mobility collapse, wrong pawn break).
4. **GREEN (positional):** implement positional detectors as played-vs-best feature diffs (reusing the Plan Explainer's diff machinery) until the golden subset passes.
5. Private calibration pass: spot-check the positional detectors against exercises from *The Woodpecker Method 2: Positional Play* (Smith, 2024) on your own machine — do detector firings agree with the book's positional themes? Use disagreements to refine predicate definitions. **No book content is committed to the repo**; the shipped fixture set remains the self-mined one.
6. Design the annotation prompt: input = FEN, played move, best line, delta, features, clock, detected motifs (both families); output = strict JSON `{description, motif_tags[], counterfactual}`. **Eval-driven boundary:** the JSON schema validator and parser get deterministic tests (malformed output, fence-stripping, retry path); annotation *quality* is spot-checked, not exact-match tested.
7. Batch 5–10 blunders per Gemini call (free-tier rate limits); annotation cache table keyed by blunder id — immutable, never regenerated.
8. Embedding service: bge-small, L2-normalized, stored alongside blunder rows.
9. Per-user FAISS `IndexFlatIP` persisted per user, incremental rebuild on new blunders, LRU cache in the worker; retrieval = SQL metadata pre-filter (phase, clock bucket, archetype, severity) → IDSelector → top-k semantic search.
10. Spot-check harness: 10 hand-picked query positions; accept ≥8 as genuinely similar, document the misses.

**Exit test:** `find_similar_blunders(fen)` returns sane neighbors on 8/10 test positions.
**Interview artifact:** "Hybrid retrieval — exact metadata filtering plus FlatIP semantic search, and why flat beats HNSW below 100k vectors."

---

## Phase 5 — The Agent Graph

**Objective:** end-to-end `analyze_game` through LangGraph, producing explanations and a versioned profile, with checkpoint resume.

1. Define `AnalysisState` (TypedDict) + pydantic models for `BlunderCandidate`, `MoveAnalysis`, `ProfileUpdate`, `ReanalysisRequest`.
2. Wrap Phase 3/4 functions as deterministic nodes: `cheap_scan`, `deep_analyze`, `profile_writer` — no LLM calls in these.
3. Psychologist node: prompt = current blunders + retrieved exemplars + current profile stats; output = pattern synthesis, `profile_delta`, optional `reanalysis_requests` (position, nodes, multipv). Voice contract in the prompt: supportive coach — honest, unsoftened numbers, fixable framing, always ends with the actionable alternative. Same contract applies to the Plan Explainer.
4. Plan Explainer node: implement PV feature-diffing (replay the PV in C++, diff Features at start/end/key points); prompt narrates only the computed diffs. Write the plan book as YAML — 2–4 canonical plans per archetype, each with a signature move/maneuver.
5. Plan consistency check: signature move present in PV → cite the named plan; absent → pure diff narration. Log pass/fail per explanation.
6. Wire the graph: conditional edge on no-candidates → explain-only path; reanalysis cycle guarded by `iteration < 3`; Postgres checkpointer.
7. Profile writer: shrinkage-smoothed stats (shrink small-n cells toward the player mean), version bump, narrative update prompt that receives the previous narrative (the profile evolves, never regenerates).
8. Integration test on a fixture game with known blunders; kill the process mid-run and assert checkpoint resume completes.

**Exit test:** `analyze_game` end-to-end on a fixture; kill/resume works; reanalysis cycle observed firing on at least one real game.
**Interview artifact:** the graph diagram — 5 deterministic nodes, 2 LLM nodes, 1 guarded cycle — and the "don't make everything an agent" argument.

---

## Phase 6 — MCP Server

**Objective:** Claude Desktop drives a full analysis with zero custom UI.

1. Server skeleton with the official MCP Python SDK, stdio transport.
2. Tools: `analyze_game(pgn|game_url)` (enqueues priority-0, streams progress as it polls), `get_player_profile(username)`, `find_similar_blunders(fen)`, `explain_plan(fen)`.
3. Expose the player profile additionally as an MCP **resource** (`profile://{username}`) — resources vs tools is a spec-literacy signal.
4. Write the Claude Desktop config snippet; document setup in the README.
5. Script and record the demo: "analyze my last game and tell me if it fits my known weaknesses" — this clip is your single best asset.

**Exit test:** full analysis driven from Claude Desktop end to end.
**Interview artifact:** the recorded clip.

---

## Phase 7 — Engine Room Frontend

**Objective:** the amber-phosphor v1 UI — board, blunder markers, streamed explanations — working on a phone.

1. Vite + React + TS scaffold; define the theme as CSS custom properties (the amber/phosphor token set from the mockup); JetBrains Mono throughout.
2. Integrate chessground; write the custom board theme (dark squares, glowing piece filter) and square-highlight layer (gold = from, ember = target).
3. Eval-cliff component: hand-rolled SVG polyline + spike dot (fits the telemetry aesthetic better than a chart lib).
4. Full game replay: move strip with every move steppable (prev/next buttons + keyboard arrows + tap-to-jump), severity glyphs (`?`, `??`) on flagged moves, eval cliff doubling as a clickable scrubber.
5. FastAPI SSE endpoint streaming analysis events (per-move ticks, blunder found, explanation chunks); React hook consuming it.
6. Flow: username entry → backfill status → game list → analysis view, plus a single-game submission box (Lichess URL or PGN paste); explanation cards render Psychologist + Plan Explainer with the plan-check verdict inline in the PV readout.
7. Mobile pass (the mockup layout already works at 390px — keep it), visible focus states, `prefers-reduced-motion` respected.

**Exit test:** on a phone, enter a username and watch an analysis stream in live.
**Interview artifact:** the live demo itself.

---

## Phase 8 — Ship

**Objective:** a stranger lands on the repo and gets it in 90 seconds.

1. README: graph diagram at the top (Mermaid), one-paragraph pitch, quickstart (`docker compose up` + token), then a **Design Decisions** section — two-pass funnel (with the measured ratio), SKIP LOCKED queue, flat-vs-HNSW, deterministic-nodes-vs-agents, PV feature-diffing, the free-stack story.
2. Surface the plan-check pass rate (your one v1 rigor metric) in the README.
3. Seed the demo with your own Lichess account: committed fixture of your analyzed games and real profile, so reviewers see genuine results without running a backfill — "here's what it found about me" is the strongest framing.
4. Record the demo GIF (web UI) + link the Claude Desktop clip.
5. Final polish: license headers, repo topics/tags, and three resume bullets drafted from the interview artifacts above.

**Exit test:** a friend who's never seen the project runs the quickstart and reaches an analyzed game without asking you anything.

---

## v2 Backlog (explicitly deferred)

Tilt modeling (time-series blunder dynamics) · predictive-validity eval harness (held-out 20 games) · failure-mode dashboard + profile diff view · hosting (Oracle free ARM + Cloudflare Pages) · SSE transport for MCP.
