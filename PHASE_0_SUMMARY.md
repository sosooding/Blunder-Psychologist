# Phase 0 — Change Summary

Scaffold for the Blunder Psychologist monorepo: a green `docker compose up` with a working
Postgres-backed job queue, before any chess logic exists. Implements Phase 0 of
[`EXECUTION_PLAN.md`](EXECUTION_PLAN.md).

Date: 2026-06-10 · Status: **complete and validated** (exit test passed).

---

## 1. What was created

### Repository root
| File | Purpose |
|---|---|
| `.gitignore` | Ignores Python/Node/C++ build artifacts, `.env`, `pgdata/`, `*.faiss`, editor/OS cruft. |
| `.dockerignore` | Keeps build contexts lean (excludes `node_modules`, `.venv`, `.git`, caches, `.env`). |
| `LICENSE` | MIT. |
| `README.md` | One-paragraph pitch, repo layout, quickstart, test instructions. |
| `.env.example` | Single config surface: `LLM_PROVIDER`, `DATABASE_URL`, `LICHESS_TOKEN`, worker tuning. |
| `compose.yaml` | 5 services: `postgres` (volume + healthcheck) → `migrate` → `api` · `worker` · `web`. |

> A local `.env` (copied from `.env.example`) is created to run the stack. It is gitignored.

### `core/` — Python package `blunder`
| File | Purpose |
|---|---|
| `pyproject.toml` | Deps (FastAPI, uvicorn, SQLAlchemy 2.0, Alembic, psycopg2-binary, pydantic-settings) + `dev` extras (pytest, ruff, httpx); ruff config (`E,F,I,UP,B`, line 100); pytest config. |
| `blunder/__init__.py` | Package version. |
| `blunder/config.py` | `Settings` (pydantic-settings) loaded from env/`.env`. |
| `blunder/db.py` | SQLAlchemy `engine` + `SessionLocal`. |
| `blunder/models.py` | ORM models for all six tables (see schema below). |
| `blunder/queue.py` | The job queue: `enqueue`, `claim_one`, `mark_done`, `mark_failed`. |
| `blunder/jobs.py` | Handler registry (`@register`) + the `hello` job. |
| `blunder/worker.py` | Poll loop: claim → dispatch → done/retry; SIGINT/SIGTERM graceful stop. |
| `blunder/api.py` | FastAPI app: `GET /health`, `POST /jobs/hello`. |
| `blunder/manage.py` | CLI: `python -m blunder.manage enqueue-hello [--name]`. |
| `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako` | Alembic setup; `env.py` reads `DATABASE_URL` from env and `blunder.models` metadata. |
| `alembic/versions/0001_initial.py` | First migration — creates all six tables, indexes, constraints. |
| `tests/conftest.py` | Session-scoped `engine` (skips if no DB) + per-test `session` (truncates `jobs`). |
| `tests/test_queue.py` | 6 tests: enqueue/claim, empty queue, priority order, SKIP LOCKED, retry→dead, mark_done. |
| `tests/test_api.py` | Health endpoint test (no DB needed). |

### `engine/` — C++ core (placeholder in Phase 0)
| File | Purpose |
|---|---|
| `CMakeLists.txt` | Trivial `blunder_engine` static lib so CI has a real target to build. |
| `include/placeholder.hpp`, `src/placeholder.cpp` | Placeholder symbol; replaced by the UCI driver + features in Phase 1. |
| `README.md` | Notes what Phase 1 fills in here. |

### `web/` — Vite + React + TS (placeholder in Phase 0)
| File | Purpose |
|---|---|
| `package.json`, `vite.config.ts`, `tsconfig.json` | Minimal Vite/React/TS setup. |
| `index.html`, `src/main.tsx`, `src/App.tsx` | Amber "BLUNDER://psychologist" splash; real UI is Phase 7. |

### `docker/`
| File | Purpose |
|---|---|
| `api.Dockerfile` | `python:3.12-slim`, installs `core`, runs uvicorn. Also used by the `migrate` service. |
| `worker.Dockerfile` | api base + apt `stockfish` + C++ toolchain (`build-essential`, `cmake`, …); runs the worker. |
| `web.Dockerfile` | `node:20-slim`, `npm install`, Vite dev server. |

### `.github/workflows/ci.yml`
Three jobs:
- **lint-test** — postgres:16 service; `ruff check` → `alembic upgrade head` → `pytest`.
- **compose-build** — `docker compose config` + build api/worker images.
- **cpp-build** — configure & build the `engine/` placeholder via CMake.

---

## 2. Data model (migration `0001`)

All six tables from the design, with the designed columns:

```
users(id, lichess_username UNIQUE, last_synced_at)
games(id, user_id→users, lichess_id UNIQUE, pgn, time_control, played_at,
      book_exit_ply, analysis_status)
move_analyses(id, game_id→games, ply, fen, move, eval_cp, best_eval_cp,
      delta_cp, sharpness, clock_seconds, phase, pawn_archetype, features JSONB)
      UNIQUE(game_id, ply)
blunders(id, move_analysis_id→move_analyses, severity, motif_tags TEXT[],
      annotation, embedding_id)
profiles(id, user_id→users, version, stats JSONB, narrative, created_at)
      UNIQUE(user_id, version)   -- append-only, versioned
jobs(id, type, priority, status, payload JSONB, attempts, last_error,
      created_at, updated_at)
      CHECK(status in pending|running|done|failed|dead)
      partial index ix_jobs_claim(priority, created_at) WHERE status='pending'
```

---

## 3. The job queue

Workers claim atomically, so two workers never grab the same row and a locked row never
blocks another:

```sql
UPDATE jobs SET status='running', attempts=attempts+1, updated_at=now()
WHERE id = (
  SELECT id FROM jobs WHERE status='pending'
  ORDER BY priority ASC, created_at ASC
  FOR UPDATE SKIP LOCKED LIMIT 1
)
RETURNING id, type, payload, attempts;
```

- **Priority lanes:** lower number drained first (on-demand = 0, backfill = 10 in later phases).
- **Retry / dead-letter:** on failure, `attempts` increments; back to `pending` until it hits
  `WORKER_MAX_ATTEMPTS` (default 3), then `dead`.
- No Redis, no Celery — plain Postgres, deliberately.

---

## 4. Notable decisions & deviations

- **Package name `blunder`.** The plan's `core/queue.py` is implemented as
  `core/blunder/queue.py` (import `from blunder.queue import enqueue`). A top-level
  `queue.py` would shadow Python's stdlib `queue` module.
- **`games.lichess_id` added** (unique) beyond the original schema sketch — needed for
  ingestion dedup in Phase 3; flagged with a code comment.
- **Stockfish via apt in the worker image**, with a comment that Phase 1 replaces it with a
  pinned official binary + NNUE net for cross-machine determinism (Phase 0 never invokes it).
- **`migrate` one-shot service** runs `alembic upgrade head`; `api`/`worker` depend on it via
  `service_completed_successfully`, so the schema always exists before they start.
- Ruff autofixed import ordering and `Union[...]`→`X | None` in `alembic/env.py` and the
  initial migration.

---

## 5. Validation performed

| Check | Result |
|---|---|
| `docker compose up --build` | postgres healthy → `migrate` applied `→ 0001` (exit 0) → api/worker/web up |
| Enqueue `hello` via CLI | job 1 → worker logged `hello, cli-world` → `done` |
| Enqueue `hello` via `POST /jobs/hello` | job 2 → worker logged `hello, http-world` → `done` |
| `GET /health` | `{"status":"ok"}` |
| pytest (in-container, real Postgres) | **7 passed** (queue SKIP LOCKED / priority / retry→dead + API) |
| `ruff check core` | clean |
| ORM mapping (`configure_mappers`) | all 6 tables configure |
| `docker compose config` | valid |

---

## 6. How to run

```bash
cp .env.example .env            # PowerShell: Copy-Item .env.example .env
docker compose up --build
# enqueue a job:
curl -X POST localhost:8000/jobs/hello -H "content-type: application/json" -d '{"name":"world"}'
# or: docker compose exec api python -m blunder.manage enqueue-hello --name world
```

Tests against the running Postgres (avoids the host port quirk below):
```bash
docker compose run --rm api sh -c "pip install -q pytest httpx && pytest -q"
```

---

## 7. Known environment quirk

A **native Windows Postgres** listens on IPv6 `::5432`, shadowing Docker's IPv4
`0.0.0.0:5432` publish. Host-side connections to `localhost:5432` (and `127.0.0.1`) can land
on the native server (auth fails for the `blunder` user). Inside the Docker network everything
resolves via the `postgres` service name. To use host tools, remap the publish to `5433:5432`
or stop the native Postgres service.

---

## 8. Next: Phase 1 — Engine Core (C++)

Deterministic, batch Stockfish analysis callable from Python, TDD-first:
RED sign-convention + determinism tests → `UciEngine` (`Threads 1`, node-limited, MultiPV 3)
→ `EnginePool` → pybind11 module `blunder_engine`. Carry in the open decision from design
review: `ucinewgame` before each stored position for order-independent determinism.
