# Project status

## Stage 1 — complete (2026-09-10)

Stage 0's exit gate was blocked by host infrastructure; it has now been cleared and re-validated end to end, and Stage 1 is implemented. No commit or push has been made by the assistant.

### Stage 0 exit gate — now passing

C: has ~20 GB free and Docker Desktop starts normally, so the earlier disk-full and WSL storage failures no longer apply.

One real defect was found and fixed while clearing the gate. The Temporal image layers cached during the disk-full event were corrupt: `/etc/passwd` and `/etc/group` inside the image were both 0 bytes, so Docker could not resolve the `temporal` user the image runs as and container creation failed with `unable to find user temporal`. Re-pulling the same digest did not repair it, because containerd still considered the corrupt content valid and re-downloaded 0 bytes. A clean `alpine` pull confirmed Docker's storage was otherwise healthy. The image was removed with the user's explicit approval and the pin moved to `temporalio/temporal:1.8.2`, whose layers download intact. No volumes were deleted; `postgres_data` and `temporal_data` were preserved.

A second, unrelated defect surfaced immediately after: the named volume is created root-owned while the image runs as uid 1000, so the dev server could not create its SQLite file (`unable to create SQLite admin DB`). Compose now runs that dev-only container as root, which keeps a fresh clone working with no manual setup step.

| Check | Result |
| --- | --- |
| `docker compose up -d --wait` | PASS: postgres and temporal both healthy |
| `alembic upgrade head` against live Postgres | PASS |
| `alembic check` | PASS: no schema drift |
| `pytest` with `RUN_INTEGRATION=1` | PASS: no tests skipped |
| `python -m app.checks all` | PASS: database and temporal |
| `python -m app.temporal.worker --smoke` | PASS |
| `npm ci` in the C: checkout | PASS: 364 packages, zero vulnerabilities |
| `npm run lint` | PASS: zero errors; one known anonymous-default-export warning in the PostCSS config |
| `npm run typecheck` | PASS |
| `npm run build` | PASS |
| HTTP GET `/` (frontend) | PASS: 200 |
| HTTP GET `/health` (backend) | PASS: `{"status":"ok","service":"orderpilot-api"}` |

The earlier D: validation copy is no longer needed; all frontend checks now pass in the repository checkout itself.

### Built in Stage 1

- `app/domain/` — pure, deterministic, I/O-free logic, safe inside the workflow sandbox and testable without a Temporal server:
  - `events.py` — event types and validating parser; unknown types survive as strings rather than being rejected.
  - `order_state.py` — explicit structured order state and a non-mutating `apply_event`.
  - `wake_policy.py` — deterministic Level A wake rules, severity table, keyword check for customer messages, unknown-event escalation, and a configurable aggressiveness threshold.
  - `decision.py` — the structured decision contract Stage 2's agent will return, with a deterministic placeholder implementation.
  - `actions.py` — the exact five assignment actions.
  - `lifecycle.py` — run statuses and explicit terminal rules.
- `app/temporal/types.py` — `RunParams` / `RunResult` contracts and `workflow_id_for_order`, giving one workflow ID per order.
- `app/temporal/workflow.py` — `OrderSupervisorWorkflow` with five Signals (`order_event`, `add_instruction`, `pause`, `resume`, `terminate`), two Queries (`state`, `timeline`), pending-event handling with `event_id` de-duplication, an in-workflow unified timeline, simple rolling memory, durable scheduled wake-ups, and deterministic finalization.
- `app/temporal/worker.py` — now registers the workflow.

Wake-ups happen on workflow start, on an important Signal, and on the durable review timer. Between wakes the workflow blocks on `wait_condition` with a timeout set to the earlier of the next review and the maximum run age; there is no polling loop. Terminal state is reached only through workflow-owned rules — a `delivered` / `refund_completed` / `order_cancelled` event, a `terminate` Signal, or the maximum age — never because a decision asked for it.

### Validation performed (2026-09-10)

| Check | Result |
| --- | --- |
| `pytest` with `RUN_INTEGRATION=1` | PASS: 29 passed, 0 skipped |
| `pytest tests/test_domain.py` | PASS: 12 domain tests |
| `pytest tests/test_workflow.py` | PASS: 12 Temporal lifecycle tests |
| `ruff check .` | PASS |
| `ruff format --check .` | PASS |
| `mypy` (strict) | PASS: 18 source files |
| Live end-to-end run against the Docker Temporal server | PASS: see below |

Workflow tests cover workflow start, Signal reception, routine events that deliberately do not wake the agent, important events that do, duplicate and malformed events, durable timer wake, pause deferring events, resume processing them, terminate while sleeping, terminate while paused, live instructions changing the next decision, terminal completion with final output, and the maximum-age rule. They run on Temporal's time-skipping test server, so durable timers are exercised without real waiting.

The live smoke ran a real worker against the Docker Temporal dev server: start woke the agent once and scheduled a sleep; `payment_confirmed` updated state without waking it; an added instruction plus `shipment_delayed` woke it and proposed `message_logistics_team` and `create_internal_note`; pause reported `PAUSED`; and `delivered` completed the run as `COMPLETED` / `delivered` with 3 events, 3 wake-ups, 1 no-wake event, and a populated final summary.

### Known limitations

- Decisions come from a deterministic placeholder, not an LLM. That is intentional for this stage.
- Proposed actions are recorded as intent only; nothing executes them yet, so there are no Activities and no action results.
- Workflow state lives only in Temporal. Nothing is written to PostgreSQL and there is no run-management API, so the timeline and memory are reachable only through Queries.
- Memory compaction is a simple line cap, not a real summarization Activity.
- The Temporal dev container runs as root to work around root-owned named volumes. Acceptable for local development only.
- Worker-restart durability is not yet demonstrated; that is Stage 5.

### Files and areas changed

- Added: `backend/app/domain/` (`__init__`, `actions`, `decision`, `events`, `lifecycle`, `order_state`, `wake_policy`), `backend/app/temporal/types.py`, `backend/app/temporal/workflow.py`, `backend/tests/test_domain.py`, `backend/tests/test_workflow.py`.
- Modified: `backend/app/temporal/worker.py` (registers the workflow), `compose.yaml` (Temporal image pin and dev-only `user: root`), `README.md`, `docs/ARCHITECTURE.md`, this file.
- Unchanged: FastAPI app, configuration, database models, migrations, and the whole frontend.

### Next stage

Stage 2 — Agent Runtime + Actions + Memory: the Pydantic agent-decision schema, one real LLM provider abstraction plus a deterministic mock, LLM inference inside Activities, the five business actions executing behind the allow-list, compact rolling memory with a compaction Activity, safe fallback for malformed model output, and a finalization Activity. Lifecycle authority stays in the workflow.

**Stage 2 has NOT been started.**
