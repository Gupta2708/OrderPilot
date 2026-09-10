# OrderPilot — Order Supervisor

Durable AI order supervisor for the original Order Supervisor PDF assignment. The PDF is the requirements source; the existing staged prompt is preserved but is not an additional requirements source.

Implemented through Stage 4, which completes P0: `OrderSupervisorWorkflow` — one durable workflow per order with Signals, Queries, durable timers, pause/resume/terminate, and workflow-owned terminal rules — the agent runtime with a Pydantic-validated decision contract, a Claude provider and a deterministic mock, the five business actions behind an allow-list, and compact rolling memory — the FastAPI control plane with everything persisted to PostgreSQL — and the operations UI: dashboard, supervisor configuration, start-run flow, Run Control Room, event simulator with scenario presets, and the final output. See [PROJECT_STATUS.md](PROJECT_STATUS.md).

**No API key is required.** The default `LLM_PROVIDER=mock` runs a deterministic agent, so the whole system can be demonstrated offline.

## Local setup (PowerShell)

Prerequisites: Node.js 24 LTS with npm, Python 3.11 or newer, [uv](https://docs.astral.sh/uv/getting-started/installation/), Docker Desktop running Linux containers, and several GB of free disk space. No API key is needed for Stage 0.

From the repository root:

```powershell
Copy-Item .env.example .env
docker compose up -d --wait
Set-Location backend
uv sync --locked
uv run --locked alembic upgrade head
uv run --locked python -m app.checks all
uv run --locked python -m app.temporal.worker --smoke
uv run --locked uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal, from the repository root:

```powershell
Set-Location frontend
npm ci
npm run dev
```

To run the scaffold worker continuously, in a third terminal from the repository root:

```powershell
Set-Location backend
uv run --locked python -m app.temporal.worker
```

The worker registers `OrderSupervisorWorkflow`, the four Activities, and the `scaffold_health` infrastructure probe. It starts no runs on its own; Stage 3 adds the API that creates them. `--smoke` starts the actual worker briefly and shuts it down cleanly.

| Service | Local address |
| --- | --- |
| Frontend | http://127.0.0.1:3000 |
| Backend liveness | http://127.0.0.1:8000/health |
| API documentation | http://127.0.0.1:8000/docs |
| Temporal UI | http://127.0.0.1:8233 |
| Temporal gRPC | 127.0.0.1:7233 |
| PostgreSQL | 127.0.0.1:5432 |

`GET /health` returns `{"status":"ok","service":"orderpilot-api"}` and checks process liveness only. `python -m app.checks all` verifies the actual database and Temporal namespace, returning a nonzero exit code on failure. The landing page does not claim infrastructure health.

## Configuration and persistence

Backend settings load the root `.env` regardless of working directory; process environment variables override it. Compose also reads root `.env`. Defaults are local development credentials only. If you change PostgreSQL credentials or its published port, update `DATABASE_URL` to match. Initialized PostgreSQL volumes retain their original credentials.

PostgreSQL holds `supervisors`, `runs`, and `activities`. Alembic manages the schema explicitly; app startup never creates tables. JSONB holds order context, decisions, and final outputs. Order IDs and Temporal workflow IDs are each unique in runs. These database constraints do not implement workflow creation.

Temporal uses the supported development server with SQLite on a separate named volume. Its history is separate from the product database. This is a local POC configuration.

Stop infrastructure without removing data using `docker compose stop`. If startup fails, check Docker Desktop, free disk space, and availability of ports 5432, 7233, and 8233. Inspect `docker compose ps` and `docker compose logs`. Backend and frontend can start independently of infrastructure. If Docker reports a missing user or unreadable image layers after a disk-full event, the cached image is corrupt: remove that image and pull it again. Do not reset Docker data or delete volumes indiscriminately.

## Validation

From `backend/`:

```powershell
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked alembic upgrade head
uv run --locked alembic check
uv run --locked python -m app.checks all
uv run --locked python -m app.temporal.worker --smoke
```

After migrations succeed, enable the Postgres round-trip and uniqueness test (its data is rolled back):

```powershell
$env:RUN_INTEGRATION = '1'
uv run --locked pytest
Remove-Item Env:RUN_INTEGRATION
```

From `frontend/`:

```powershell
npm ci
npm run lint
npm run typecheck
npm run build
```

With both apps running:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
(Invoke-WebRequest http://127.0.0.1:3000 -UseBasicParsing).StatusCode
```

`npm ci` is required before running the frontend. The lockfile preserves the successfully resolved versions. ESLint 9 is retained because the attempted version 10 update produced transitive peer warnings and was interrupted; its support warning is a known tooling limitation.

Workflow lifecycle tests run against Temporal's time-skipping test server, which downloads a test-server binary on first use and needs network access once.

## Workflow behaviour (Stage 1)

One workflow per order, with the ID `order-supervisor:<order_id>`, so Temporal's ID uniqueness guarantees a single supervisor per order.

| Signal | Effect |
| --- | --- |
| `order_event` | Validated, de-duplicated by `event_id`, queued for processing |
| `add_instruction` | Appends live run guidance used by every later decision |
| `pause` / `resume` | Suspends and restores normal event processing |
| `terminate` | Ends the run, including while sleeping or paused |

| Query | Returns |
| --- | --- |
| `state` | Status, order state, memory, instructions, latest decision, next wake, counters |
| `timeline` | The recent unified activity entries |

The agent is woken on workflow start, on an important Signal, and on the durable review timer. Routine events such as `payment_confirmed` update state without waking it. Between wakes the workflow waits on a durable Temporal timer rather than polling.

Terminal conditions are owned by the workflow, never by a decision: a `delivered`, `refund_completed`, or `order_cancelled` event; a `terminate` Signal; or the configured maximum run age.

## Agent runtime (Stage 2)

Decisions are made in an Activity, never in workflow code, and every decision is validated with Pydantic before it can affect anything.

| Setting | Meaning |
| --- | --- |
| `LLM_PROVIDER=mock` | Default. Deterministic decisions, no API key, no network. |
| `LLM_PROVIDER=claude` | Real provider via the Anthropic SDK. Needs `ANTHROPIC_API_KEY`. |
| `ANTHROPIC_MODEL` | Defaults to `claude-opus-5`. |

The agent returns a fixed structure: decision, priority, one-or-two-sentence reason summary, actions, memory update, sleep interval, and a completion recommendation. Anything outside that schema is rejected. Tool names are constrained by the schema itself, then filtered again against the supervisor's allowed actions, and re-checked once more at execution time.

If the provider fails or returns something unvalidatable, the Activity retries once and then uses a deterministic fallback that takes no action and schedules an ordinary review, so a provider outage degrades to a quiet supervisor rather than a wrong one. Fallback use is counted and surfaced in the final recommendations.

The five actions — `message_fulfillment_team`, `message_payments_team`, `message_logistics_team`, `message_customer`, `create_internal_note` — are simulated, and each execution returns a structured success/failure result recorded on the timeline.

The agent can recommend completion, but it cannot cause it. Terminal state remains owned by the workflow rules above.

## API (Stage 3)

All endpoints are under `/api`. Interactive docs are at http://127.0.0.1:8000/docs.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/supervisors` | Create a supervisor configuration |
| GET | `/api/supervisors` | List supervisors |
| GET | `/api/supervisors/{id}` | Fetch one supervisor |
| POST | `/api/runs` | Create a run and start its workflow |
| GET | `/api/runs` | List runs, optionally `?status=` |
| GET | `/api/runs/{run_id}` | Persisted record: state, memory, timeline, final output |
| GET | `/api/runs/{run_id}/state` | Live workflow state, falling back to the database |
| POST | `/api/runs/{run_id}/events` | Deliver a lifecycle event as a Signal |
| POST | `/api/runs/{run_id}/instructions` | Add a live run instruction |
| POST | `/api/runs/{run_id}/pause` | Pause the run |
| POST | `/api/runs/{run_id}/resume` | Resume the run |
| POST | `/api/runs/{run_id}/terminate` | Terminate the run |

Starting a run writes the run row and then starts exactly one workflow, keyed `order-supervisor:<order_id>`. A second run for the same order returns 409. Events, instructions, and controls are Signals; the workflow de-duplicates events by `event_id`, and the API generates one when the caller omits it. Controls return 202 because they are asynchronous: the Signal is accepted, and the workflow applies it on its next step.

Error mapping: 404 for an unknown supervisor or run, 409 for a duplicate order or a workflow that is no longer accepting signals, 422 for invalid input such as an unknown action name, and 503 when Temporal is unreachable. The API still serves reads when Temporal is down.

The workflow persists its own progress: it buffers timeline rows and writes them, with current run state, through a persistence Activity. Rows carry a per-run sequence number with a unique constraint, so a retried write cannot duplicate history.

**All three processes are needed for a working system.** The API starts workflows, the worker executes them, and the frontend drives the API. With the worker stopped, runs are created but never progress.

Running the backend end to end:

```powershell
Set-Location backend
uv run --locked alembic upgrade head
uv run --locked python -m app.temporal.worker      # terminal 1
uv run --locked uvicorn app.main:app --port 8000   # terminal 2
```

## Using the app (Stage 4)

Open http://127.0.0.1:3000 with all three processes running.

1. **Supervisors** — create a supervisor: its instruction, which of the five actions it may take, how eagerly it wakes, its review interval, and its maximum run age.
2. **Start run** — give an order ID and some context, pick a supervisor, and optionally add an instruction that applies to this run only.
3. **Run Control Room** — the main screen. It shows the live workflow status, a countdown to the next wake, structured order state, compact memory, the latest decision and the wake decision behind it, the unified timeline, action history, run instructions, the event simulator, and pause/resume/terminate. When the run ends it shows the final summary, learnings, and recommendations.

The **event simulator** drives an order forward one event at a time. It carries the four assignment scenarios — Happy Path, Payment Trouble, Delivery Crisis, Refund Risk — and can inject any single event, including an unrecognised type so unknown-event handling can be demonstrated.

The clearest thing to demonstrate is the difference between events: `payment_confirmed` updates the order state and the wake card explains that the agent was deliberately *not* woken, while `shipment_delayed` wakes it immediately and produces an escalation. Adding the instruction "If shipment is delayed, escalate immediately." before injecting the delay shows live instructions changing the next decision.

The UI polls the API every two seconds. Runs progress on their own, so state changes without a refresh.

`NEXT_PUBLIC_API_BASE_URL` overrides the API location; see `frontend/.env.example`. The default works with the setup above.

See [architecture](docs/ARCHITECTURE.md). Stage 5 adds the AI wake classifier, the human approval gate, and the worker-restart durability demo.
