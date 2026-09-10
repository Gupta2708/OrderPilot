# Project status

## Stage 3 — complete (2026-09-10)

Stage 2 was committed and pushed by the user as `de895af`. The working tree was clean at the start of this stage and both Docker services were healthy. Stage 3 adds persistence and the FastAPI control plane, completing the P0 backend. No commit or push has been made by the assistant.

### Built in Stage 3

- Migration `0002_run_persistence` — adds `runs.last_wake_at`, `runs.stats`, `activities.seq`, and a unique `(run_id, seq)` constraint that makes persistence retry-safe. Models updated to match; `alembic check` reports no drift.
- `app/repository.py` — database access for supervisors, runs, and the unified timeline, including `save_run_snapshot`, which upserts run state and inserts new activity rows with `ON CONFLICT DO NOTHING`.
- `app/temporal/activities.py` — new `persist_snapshot` Activity, with one engine per worker process.
- `app/temporal/workflow.py` — buffers timeline rows and flushes them with current run state after the start wake, after each event drain, after each scheduled review, before parking on a pause, and at finalization. The final output is persisted with `completed_at`.
- `app/services/runs.py` — run creation, workflow start, and the mapping from product operations to Signals and Queries, kept out of the HTTP handlers.
- `app/api/` — `deps.py` (request-scoped session, Temporal client), `schemas.py`, `supervisors.py`, `runs.py`.
- `app/main.py` — lifespan that opens the database engine and Temporal client once per process. A missing Temporal service degrades to 503 on control endpoints rather than failing startup, so reads keep working.

All twelve endpoints from the assignment are implemented. Starting a run writes the run row and then starts exactly one workflow keyed `order-supervisor:<order_id>`; a duplicate order returns 409. Events, instructions, and controls are Signals and return 202. Errors map to 404 (unknown supervisor or run), 409 (duplicate order, or a workflow no longer accepting signals), 422 (invalid input, including unknown action names), and 503 (Temporal unreachable).

**One design decision worth noting:** the API never writes run progress. It starts workflows and sends Signals; the workflow persists its own state. That keeps a single writer for run progress and avoids the API and the workflow racing to describe the same run.

**One real defect found and fixed during this stage.** A Signal that only writes a timeline row — a duplicate event, a rejected event, an instruction while the run is idle — left the workflow parked in `wait_condition`, so that row was never flushed to Postgres until the next unrelated wake. The end-to-end test caught it. The wait condition now also wakes on unflushed rows.

### Validation performed (2026-09-10)

| Check | Result |
| --- | --- |
| `pytest` with `RUN_INTEGRATION=1` | PASS: 64 passed, 0 skipped |
| `pytest tests/test_end_to_end.py` | PASS: full P0 backend over HTTP |
| `pytest tests/test_api.py` | PASS: 13 API contract tests |
| `pytest tests/test_workflow.py` | PASS: 15 Temporal lifecycle tests |
| `pytest tests/test_agent.py` | PASS: 18 agent runtime tests |
| `pytest tests/test_domain.py` | PASS: 12 domain tests |
| `ruff check .` / `ruff format --check .` | PASS |
| `mypy` (strict) | PASS: 32 source files |
| `alembic upgrade head` and `alembic check` | PASS: no drift |
| Live run driven through the HTTP API | PASS: see below |

`tests/test_end_to_end.py` is the Stage 3 exit gate: a real worker, a real workflow on Temporal's time-skipping test server, a real database, and the real routers. It walks the whole P0 backend — configure a supervisor, start a run, confirm the start wake is persisted, confirm live state comes from the workflow, confirm a routine event updates state without waking the agent, add an instruction and inject `shipment_delayed` to drive a real action, confirm a duplicate event is ignored, pause and resume, then complete via `delivered` and confirm the final output, ordered gap-free timeline, and database-sourced state after closure. It commits, so it cleans up its own rows.

`tests/test_api.py` runs against a real database with a faked Temporal client, inside a rolled-back transaction, and covers HTTP status mapping, duplicate orders, unknown supervisors and runs, signal routing, event-id preservation, and the live-versus-database state fallback.

The live check ran the real worker and Uvicorn against Docker Temporal and Postgres, exercising the lifespan wiring the tests bypass. Creating a supervisor and a run, adding an instruction, injecting `payment_confirmed` and `shipment_delayed`, then `delivered`: the run reached `COMPLETED` with 22 persisted timeline rows, 3 wake-ups, 1 no-wake event, 3 executed actions, compact memory across three notes, and a populated final output.

### Known limitations

- **The Claude provider path still has not been executed against the live API** (no key on this machine). Everything ran on the deterministic mock. Unchanged from Stage 2 and still the main thing to verify before a demo that claims live AI.
- No UI yet; that is Stage 4.
- `GET /api/runs` returns every run with no pagination. Fine at POC scale, wrong at real scale.
- Persistence flushes at wake boundaries, so between a Signal and the next flush the database can lag the workflow by a moment. `GET /api/runs/{id}/state` reads the workflow directly and is the authoritative view.
- If the worker is not running, runs are created but never progress. Both processes are required, and the README now says so.
- The wake classifier, approval gate, and worker-restart durability demo remain Stage 5; analytics and Continue-As-New remain Stage 6.
- One demo supervisor and one completed run from the live check were deliberately left in the local development database as useful seed data for the Stage 4 dashboard.

### Files and areas changed

- Added: `backend/migrations/versions/0002_run_persistence.py`, `backend/app/repository.py`, `backend/app/services/` (`__init__`, `runs`), `backend/app/api/` (`__init__`, `deps`, `schemas`, `supervisors`, `runs`), `backend/tests/test_api.py`, `backend/tests/test_end_to_end.py`.
- Modified: `backend/app/main.py` (routers and lifespan), `backend/app/models.py`, `backend/app/db.py` (session factory), `backend/app/temporal/activities.py` (`persist_snapshot`), `backend/app/temporal/workflow.py` (flush points and the wait-condition fix), `backend/tests/test_workflow.py` (stubs persistence so lifecycle tests stay database-free), `README.md`, `docs/ARCHITECTURE.md`, this file.
- Unchanged: the agent runtime, the domain layer, `compose.yaml`, `.env.example`, and the whole frontend.

### Next stage

Stage 4 — Product UI + Event Simulator + Complete P0: the dashboard, supervisor configuration, start-run screen, Run Control Room with status badges, order-state card, next-wake display, memory card, decision and wake-reason cards, unified timeline, action history, event injector, instruction input, pause/resume/terminate controls, final output, and the four scenario presets.

**Stage 4 has NOT been started.**
