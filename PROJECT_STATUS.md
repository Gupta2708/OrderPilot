# Project status

## Stage 2 — complete (2026-09-10)

Stage 1 was committed and pushed by the user as `80e0bd9`. The working tree was clean at the start of this stage; both Docker services were healthy and were re-verified before starting. Stage 2 adds the agent runtime on top of the durable workflow. No commit or push has been made by the assistant.

### Built in Stage 2

- `app/agent/schema.py` — the Pydantic decision contract. Tool names are a closed enum in the schema, so an invented tool fails validation rather than reaching the allow-list. `normalize()` then resolves the sleep specification to a bounded integer and filters actions against the supervisor's allowed list, returning the rejected names so the rejection is auditable. An `ACT` whose every tool was rejected is downgraded to `NO_ACTION`.
- `app/agent/provider.py` — one provider interface with two implementations. `ClaudeProvider` uses the Anthropic SDK's structured-output parse endpoint with `claude-opus-5` and server-side refusal fallbacks. `MockProvider` is deterministic, needs no key or network, and is the default. `deterministic_fallback()` never acts.
- `app/agent/prompt.py` — compact per-decision context: supervisor instruction, live run instructions, structured order state, memory, triggering event, wake evaluation, a short recent-activity window, and allowed actions. Raw history is never sent.
- `app/agent/execution.py` — the five business actions, simulated, each returning a structured success/failure result; plus deterministic memory compaction with a line cap, a dropped-note marker, and a character cap.
- `app/temporal/activities.py` — four Activities: `make_decision`, `run_business_action`, `compact_run_memory`, `finalize_run`.
- `app/temporal/workflow.py` — rewired to call those Activities with explicit timeouts and retry policies. The workflow still performs no I/O and its lifecycle rules are unchanged.
- Configuration: `LLM_PROVIDER` (default `mock`), `ANTHROPIC_MODEL` (default `claude-opus-5`), `ANTHROPIC_API_KEY`, all documented in `.env.example`.

The action allow-list is enforced three times: the schema constrains tool names, the Activity filters against the supervisor configuration, and execution re-checks before running anything.

### Validation performed (2026-09-10)

| Check | Result |
| --- | --- |
| `pytest` with `RUN_INTEGRATION=1` | PASS: 50 passed, 0 skipped |
| `pytest tests/test_agent.py` | PASS: 18 agent runtime tests |
| `pytest tests/test_workflow.py` | PASS: 15 Temporal lifecycle tests |
| `pytest tests/test_domain.py` | PASS: 12 domain tests |
| `ruff check .` | PASS |
| `ruff format --check .` | PASS |
| `mypy` (strict) | PASS: 24 source files |
| Live end-to-end run against the Docker Temporal server | PASS: see below |

New tests cover schema validation and rejection of malformed output, rejection of invented tool names, allow-list filtering with the rejected tools reported, `ACT` downgraded when all tools are rejected, sleep clamping and timestamp conversion, execution of all five actions, refusal of disallowed and unknown tools, safe defaults for missing arguments, memory compaction and de-duplication, mock determinism, the deterministic fallback when the provider fails, and prompt composition. Two workflow tests cover the Stage 2 exit criteria directly: a stub provider that recommends completion on every decision cannot end a run (only a later `delivered` event does), and a disallowed tool is never executed end to end.

The live smoke ran a real worker against the Docker Temporal dev server with the mock provider: start woke the agent and slept; `payment_confirmed` updated state without waking it; an instruction plus `shipment_delayed` woke the agent, which executed `message_logistics_team` and `create_internal_note` and updated compact memory; pause reported `PAUSED`; `delivered` completed the run as `COMPLETED` / `delivered` with 3 events, 3 wake-ups, 3 executed actions, 0 failed, 0 rejected, 0 fallback decisions, and a populated final summary.

### Known limitations

- **The Claude provider path has not been executed against the live API.** No `ANTHROPIC_API_KEY` is available on this machine, so it was verified only by checking the call against the installed SDK's actual signatures (`anthropic` 1.4.0: `client.beta.messages.parse` accepts `output_format`, `betas`, and `fallbacks`) and by strict type checking. Every test and the live smoke ran on the mock provider. This needs one real call before any demo that claims live AI.
- Nothing is persisted to PostgreSQL yet and there is no API, so state is reachable only through Temporal Queries. That is Stage 3.
- Memory compaction is deterministic truncation, not summarization. Reasonable at this size, but it will lose detail on very long runs.
- The wake policy is still deterministic only; the lightweight AI classifier is Stage 5, as is the human approval gate for `message_customer`.
- Actions are simulated, as the assignment allows.
- Worker-restart durability is still not demonstrated; that is Stage 5.
- The Temporal dev container still runs as root to work around root-owned named volumes. Local development only.

### Files and areas changed

- Added: `backend/app/agent/` (`__init__`, `schema`, `provider`, `prompt`, `execution`), `backend/app/temporal/activities.py`, `backend/tests/test_agent.py`.
- Modified: `backend/app/temporal/workflow.py` (calls Activities; lifecycle rules unchanged), `backend/app/temporal/worker.py` (registers Activities), `backend/app/config.py` (provider settings), `backend/pyproject.toml` and `backend/uv.lock` (added `anthropic`), `backend/tests/test_workflow.py` (register Activities, wait on decision results, three new tests), `.env.example`, `README.md`, `docs/ARCHITECTURE.md`, this file.
- Unchanged: FastAPI app, database models, migrations, `compose.yaml`, and the whole frontend.

### Stage 0 and Stage 1 status

Both remain green. The Stage 0 exit gate was cleared earlier today after repairing a corrupt cached Temporal image and a root-owned volume; those fixes are in `compose.yaml` and were committed in `80e0bd9`.

### Next stage

Stage 3 — Persistence + FastAPI + End-to-End P0 Backend: persist supervisors, runs, unified activities, order state, memory, latest decision, and final outputs; implement the supervisor/run/event/instruction/control endpoints; start workflows from the API and map events and controls onto Signals; expose timeline, memory, and final output over HTTP.

**Stage 3 has NOT been started.**
