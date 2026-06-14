# Blunder Psychologist

A chess improvement system that models **your individual failure modes** — not generic engine
analysis, but a psychological profile of *how you specifically lose*, grounded in your own game
history via RAG, with a Plan Explainer that turns engine lines into verified strategic narratives.

**Stack:** C++ analysis engine (Stockfish/UCI, pybind11) · Python agent layer (LangGraph,
LangChain, FAISS, MCP) · TypeScript/React frontend · PostgreSQL · Docker.
Entirely free to run: Gemini Flash / Ollama behind one env var, local bge-small embeddings,
Postgres-backed job queue, Oracle free-tier hosting path.

---

## Architecture

```mermaid
flowchart LR
  L[Lichess API] --> I[Ingestion\npython-chess]
  I --> Q[(Postgres\n+ job queue)]
  Q --> F[Two-pass funnel]
  F --> E[C++ engine core\nStockfish UCI · pybind11\nfeatures · archetypes]
  E --> Q
  Q --> A[Annotation\nmotif detectors + LLM]
  A --> V[(FAISS\nper-user flat indexes)]
  Q --> G[LangGraph\n5 deterministic + 2 LLM nodes]
  V --> G
  G --> P[(Versioned profiles)]
  G --> M[MCP server\nstdio]
  G --> W[React frontend\nEngine Room theme]
```

```mermaid
flowchart TD
  S([start]) --> CS[cheap_scan]
  CS -->|no candidates| PE
  CS -->|candidates| DA[deep_analyze · C++]
  DA --> PSY[🧠 psychologist · LLM]
  PSY -->|reanalysis_requests\n& iteration < 3| DA
  PSY --> PE[🧠 plan_explainer · LLM]
  PE --> PW[profile_writer]
  PW --> E([end])
```

Multi-user from day one (Lichess username = identity, no auth in v1). On-demand single-game
analysis (by Lichess URL or PGN paste) jumps the backfill queue at priority 0.

---

## Status

**Phase 0 — Scaffold complete.** `docker compose up` is green: Postgres with a priority job
queue (`SELECT … FOR UPDATE SKIP LOCKED`), all six schema tables, Alembic migrations, FastAPI
health endpoint, worker poll loop, and a `hello` job end-to-end.

**Phase 1 — Engine core complete.** Deterministic, batch Stockfish analysis callable from
Python: a `Threads 1`, node-limited UCI driver with `ucinewgame` per position, mate-aware
eval-delta semantics fixed by hand-computed tests, a pool that analyzes whole PGNs reproducibly,
and the `blunder_engine` pybind11 wheel (GIL released). The Catch2 suite — sign conventions plus
byte-identical determinism — is green in CI against a pinned Stockfish (`sf_18`). See
[`engine/`](engine/).

**Phase 2 — Features & archetypes complete.** Every analyzed position now carries a positional
feature vector and a pawn-structure archetype, built test-first. Hand-coded bitboard predicates
(isolated / doubled / backward / passed pawns, open & half-open files, king-shield integrity)
feed an ordered-predicate classifier over the 12 canonical structures with an honest `unknown`
class, validated by a golden-FEN suite. A MultiPV-3 sharpness metric and a sharpness-scaled
severity classifier (inaccuracy / mistake / blunder, suppressed once the game is already decided)
finish each move. The feature layer is Stockfish-free and lives in its own library
(`blunder_features`); its golden-FEN and predicate suites run in CI without an engine binary. The
pybind11 output now exposes `features`, `archetype`, `sharpness`, and `severity` per move.

**Phase 3 — Ingestion & the two-pass funnel complete.** Type a Lichess username and the system
backfills it unattended: an NDJSON-streaming client (429 backoff) pulls rated rapid/classical
games, a stratified sampler picks ~300 recent + ~100 older, and each game is parsed with
python-chess (per-move clocks + embedded `[%eval]`). Book exit is detected per game via the
opening explorer (cached by FEN in `opening_cache`, flat move-10 fallback). The **cheap pass**
thresholds Lichess eval-deltas on the profiled user's post-book moves for free, falling back to a
100k-node engine scan only where evals are absent; the **deep pass** turns each candidate into a
minimal `[SetUp]`/`[FEN]` one-move PGN so the C++ engine re-evaluates *only* candidate positions
at 2M nodes — that is where the funnel saves its compute. Priority lanes (on-demand single game =
0, backfill chunks of 25 = 10), incremental sync via `last_synced_at`, and FastAPI endpoints
(`POST /users/{u}/backfill`, `POST /games/analyze`, `GET /users/{u}/status`) round it out. The
funnel ratio is logged per chunk. Built test-first: a committed NDJSON fixture drives the client,
sampler, parser, book-exit, and cheap-pass unit tests, and an end-to-end test runs the whole
backfill→scan→deep chain through the real queue and Postgres with a fake transport and analyzer.

**Phase 4 — Annotation & RAG complete.** Every blunder now gets a grounded, motif-tagged
annotation and is retrievable by similarity. Motifs are detected in code first — tactical
(`hanging_piece`, `fork`, `pin`, `back_rank`) via a static-exchange evaluator over the
post-blunder board, positional (`structure_damage`, `king_shield_weakening`, `mobility_collapse`)
via played-vs-best feature diffs through a new Stockfish-free `extract_features` engine binding.
The LLM (Gemini Flash or local Ollama, behind one env var) writes only the *why* and the
counterfactual as strict JSON over a closed tag vocabulary — fence-stripping, off-vocabulary
rejection, and a retry path are all deterministically tested. Annotations are batched, immutable,
and embedded with local bge-small (fastembed); per-user FAISS `IndexFlatIP` retrieval does a SQL
metadata pre-filter (phase × archetype × severity) then top-k semantic search. An `annotate` job
runs after each deep analysis; `find_similar_blunders(fen)` and `GET /users/{u}/similar` expose
retrieval. Built test-first: detector benchmarks, the JSON-boundary suite, and an end-to-end
annotate-and-retrieve test through real Postgres with fakes for the engine, LLM, and embedder.

Later phases add the agent graph, the MCP server, and the Engine Room UI. See
[`EXECUTION_PLAN.md`](EXECUTION_PLAN.md) for the phased build and [`DESIGN.md`](DESIGN.md) for full
architecture details.

---

## Repository layout

```
engine/   C++ analysis core — Stockfish UCI driver, features, archetypes (placeholder in Phase 0)
core/     Python: FastAPI api, worker, Postgres job queue, SQLAlchemy models, Alembic migrations
web/      TypeScript/React (Vite) frontend — Engine Room theme (placeholder in Phase 0)
docker/   Dockerfiles for api, worker, web
```

---

## Quickstart

```bash
cp .env.example .env          # PowerShell: Copy-Item .env.example .env
# Edit .env: set LICHESS_TOKEN to your token from https://lichess.org/account/oauth/token
docker compose up --build
```

This starts Postgres, runs migrations, and brings up the api, worker, and web dev server.

Enqueue a `hello` job and watch the worker pick it up:

```bash
curl -X POST localhost:8000/jobs/hello \
  -H "content-type: application/json" \
  -d '{"name":"world"}'
# or, without the API:
docker compose exec api python -m blunder.manage enqueue-hello --name world
```

The worker log prints `hello, world` and marks the job `done`.

- API:  http://localhost:8000  (`GET /health`)
- Web:  http://localhost:5173

**Windows note:** if a native Postgres is already running, it listens on `::5432` (IPv6) and can
shadow Docker's published port. Host-side connections to `localhost:5432` may land on the native
server and fail auth. Inside the Docker network everything routes via the `postgres` service name
correctly; for host tools, remap the publish to `5433:5432` or stop the native service.

---

## Tests

Run against the live Postgres service (the job queue uses `SKIP LOCKED`, which SQLite doesn't
support):

```bash
# inside the running stack — avoids the Windows host-port quirk
docker compose run --rm api sh -c "pip install -q pytest httpx && pytest -q"
```

Or locally with a real Postgres:

```bash
cd core
pip install -e ".[dev]"
export DATABASE_URL=postgresql+psycopg2://blunder:blunder@localhost:5432/blunder
pytest -q
```

---

## Design decisions

### Two-pass analysis funnel

Naive full-history analysis at 2 M nodes/move takes hours per user. Instead:

1. **Cheap pass** — Lichess's embedded server evals (where present) or a 100 k-node scan flags
   candidate blunders by eval-delta threshold.
2. **Expensive pass** — the full C++ pipeline (2 M nodes, MultiPV 3, feature extraction) runs
   only on candidates, and only on the profiled user's moves (opponent positions are evaluated
   only as delta inputs, never stored as blunders).

Book moves don't count: book exit is detected per game via the Lichess opening explorer (cached
by FEN, flat move-10 fallback) and stored as `games.book_exit_ply`. Blunder-opportunity counting
starts there. Bullet games excluded entirely.

Target funnel ratio: ~10x fewer deep-analyzed positions than total positions. As of Phase 3 the
funnel is implemented end-to-end and logs the measured ratio (total plies ÷ candidate plies, e.g.
`12.0x`) per scanned chunk; the headline number from a real backfill is filled in once the demo
account is seeded (Phase 8).

### Postgres job queue — no Redis, no Celery

Workers claim atomically with `SELECT … FOR UPDATE SKIP LOCKED`: two workers never grab the same
row, a locked row never blocks another. Priority lanes (lower number first): on-demand = 0,
backfill chunks = 10. Failed jobs retry up to `WORKER_MAX_ATTEMPTS` then go `dead`. One
dependency eliminated, one failure mode eliminated.

### Flat FAISS over HNSW/IVF

Per-user corpora are 2–10 k vectors. Exact search (`IndexFlatIP`) is cheap below ~100 k and the
ANN approximation overhead is unjustified at this scale. The retrieval pipeline is hybrid: SQL
metadata pre-filter (phase × clock bucket × archetype × severity) → FAISS IDSelector → top-k
semantic search with bge-small embeddings.

### Deterministic nodes vs. LLM agents

Two LLM nodes only — Psychologist and Plan Explainer. Everything else (cheap scan, deep analyze,
profile writer) is a plain deterministic function node. The agent graph isn't smart; it's a
controlled pipeline with two reasoning steps at the boundaries where reasoning actually adds
value.

### Plan Explainer — PV feature-diffing, not free narration

Anti-hallucination by construction: the principal variation is replayed in C++ and positional
features are diffed at start/end/key points (e.g. "e-file opens, d5 becomes passed, Black's king
shield loses the f-pawn"). The LLM narrates only these computed facts. A curated plan book (YAML,
2–4 canonical plans per archetype with a signature move) adds a consistency check: the signature
move must appear in the PV before the named plan may be cited. **Plan-check pass rate** is the
one shipped rigor metric in v1 and will be reported here once Phase 5 ships.

### Pawn archetypes — hand-coded predicates over ML

12 structures (Carlsbad, IQP, hanging pawns, Maróczy, Hedgehog, Stonewall, French chain, KID
chain, symmetric open/closed, opposite-castling race, endgame-simplified) as ordered bitboard
predicates with an honest `unknown` class. Rules over ML: explainable, debuggable, every line
defensible.

### Free stack

Gemini Flash (free tier, configurable) or Ollama (fully local) behind one env var. bge-small
embeddings run locally. Postgres for everything persistent. Oracle free-tier ARM is the v2
hosting path. No paid infrastructure required to run or develop.

---

## MCP (Claude Desktop)

Phase 6 exposes a stdio MCP server with tools `analyze_game`, `get_player_profile`,
`find_similar_blunders`, `explain_plan`, and the player profile as a resource
(`profile://{username}`). Claude Desktop becomes a full frontend with zero custom UI. Setup
instructions and the demo clip will be added when Phase 6 ships.

---

## License

MIT
