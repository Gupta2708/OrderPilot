# Project status

## Stage 4 — complete (2026-09-10). P0 is done.

Stage 3 was committed and pushed by the user as `400f891`. The working tree was clean at the start of this stage. Stage 4 adds the operations UI and the event simulator, which completes the P0 acceptance criteria: every assignment requirement can now be demonstrated from a browser. No commit or push has been made by the assistant.

### Built in Stage 4

- `lib/api.ts` — typed API client with a single error path. Network failures and FastAPI validation errors both become readable messages instead of raw statuses.
- `lib/types.ts`, `lib/format.ts`, `lib/scenarios.ts`, `lib/use-polling.ts` — shared types, countdown and duration formatting, the four scenario presets, and one polling hook every screen uses.
- `components/ui.tsx` — status and severity badges, cards, stats, buttons, error banners.
- `components/run-cards.tsx` — order state, latest decision, wake decision, compact memory, unified timeline, action history, and final output.
- `components/event-simulator.tsx` — scenario presets driven one step at a time, plus arbitrary event injection including an unrecognised type.
- `app/page.tsx` — dashboard with acting / sleeping / attention / completed buckets and a run table.
- `app/supervisors/page.tsx` — supervisor list and configuration form.
- `app/runs/new/page.tsx` — start-run flow with order context and an optional per-run instruction.
- `app/runs/[runId]/page.tsx` — the Run Control Room.
- `app/layout.tsx`, `app/icon.svg`, `frontend/.env.example`.

The UI holds no business logic. It renders what the API reports and turns operator intent into API calls; every fact on screen already exists in the workflow or the database. Live workflow state is preferred and labelled as such, with the persisted record as the fallback, so a completed run still renders after its workflow closes.

### Validation performed (2026-09-10)

| Check | Result |
| --- | --- |
| `npm run lint` | PASS: 0 errors; 1 known PostCSS anonymous-default-export warning |
| `npm run typecheck` | PASS |
| `npm run build` | PASS: 6 routes generated |
| Backend `pytest` with `RUN_INTEGRATION=1` | PASS: 64 passed, 0 skipped |
| Backend `ruff check` / `ruff format --check` / `mypy` strict | PASS |
| Headless-browser walkthrough of the whole product | PASS: 8 of 8 checks, no console or page errors |

The browser walkthrough drove the real UI against the real stack — Next.js production build, FastAPI, the worker, Temporal, and Postgres — and covered: creating a supervisor and seeing it listed; starting a run and landing on its control room; the control room rendering live workflow state; running the Delivery Crisis scenario step by step until an escalation action executed and appeared in action history; pause reaching `PAUSED`; resume; completion showing the final summary, learnings, and recommendations; the dashboard reflecting the completed run; and a 420px viewport with no horizontal overflow. Screenshots were captured for each step.

Two issues surfaced during that walkthrough and both were fixed: a missing favicon returned 404 on every page, now served from `app/icon.svg`; and the React compiler lint rule rejected the initial data-loading effects, which is now handled by one documented `usePolling` hook rather than scattered suppressions. A third apparent error — a chunk-loading 500 — was an artifact of my own restart sequence, where a stale `next start` process kept port 3000 while its `.next` directory was rebuilt underneath it. It does not reproduce on a clean start, and the final walkthrough ran with zero browser errors.

### Known limitations

- **The Claude provider path still has not run against the live API.** No `ANTHROPIC_API_KEY` is available on this machine, so every run above used the deterministic mock. Unchanged since Stage 2 and still the single most important thing to verify before demonstrating live AI.
- The UI polls every two seconds rather than streaming. Fine locally; it would need rethinking at scale.
- No pagination anywhere: the dashboard lists every run and the timeline is capped at 200 entries server-side.
- No authentication. Anyone who can reach the API can control any run.
- Supervisors can be created but not edited or deleted from the UI.
- The approval gate for `message_customer` is not built yet, so the UI has no pending-approval state. That is Stage 5, along with the AI wake classifier and the worker-restart durability demo.
- Several demo supervisors and completed runs from the walkthrough remain in the local development database as seed data.

### Files and areas changed

- Added: `frontend/lib/` (`api`, `types`, `format`, `scenarios`, `use-polling`), `frontend/components/` (`ui`, `run-cards`, `event-simulator`), `frontend/app/supervisors/page.tsx`, `frontend/app/runs/new/page.tsx`, `frontend/app/runs/[runId]/page.tsx`, `frontend/app/icon.svg`, `frontend/.env.example`.
- Modified: `frontend/app/layout.tsx` (nav shell), `frontend/app/page.tsx` (landing page replaced by the dashboard), `README.md`, `docs/ARCHITECTURE.md`, this file.
- Unchanged: the entire backend. No API, workflow, agent, or database change was needed for this stage, which is a good sign for the Stage 3 contract.

### P0 acceptance criteria

All assignment P0 requirements are now demonstrable from the browser: one durable workflow per order; lifecycle events as Signals; wake on start, on important events, and on a durable timer; unimportant events updating state without invoking the main agent; structured business actions from an allow-list; compact memory plus an auditable timeline; durable sleep instead of polling; live run instructions; pause, resume, and terminate; workflow-owned completion; and a final summary with important actions, learnings, and recommendations.

### Next stage

Stage 5 — P1: the lightweight AI wake classifier for ambiguous and unknown events, wake/no-wake audit records, unknown-event escalation, the human approval gate for sensitive actions with a configurable requirement for `message_customer`, approve/reject in the backend and UI, a pending-approval state, decision cards, stronger scenario behaviour, and a documented worker-restart durability demonstration.

**Stage 5 has NOT been started.**
