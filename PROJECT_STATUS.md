# Project status

## Stage 7 — complete (2026-09-10). The project is submission-ready.

Stage 6 was committed and pushed by the user as `dc0f3a1`. Stage 7 is final hardening, documentation, and submission readiness. All seven stages are now done: P0, P1, and P2 are complete. No commit or push has been made by the assistant.

### Done in Stage 7

**Repository housekeeping.** `ORDER_PILOT_STAGED_BUILD_PROMPT.md` is now untracked and gitignored, at the user's request. The local file is untouched; only the Git index changed. Note that the file still exists in earlier commits already pushed to GitHub — removing it from history would need a rewrite (`git filter-repo` or BFG) and a force push, which was not done.

**Dead code removed.** `DECISION_JSON_SCHEMA_HINT` (computed, never used), `count_runs_by_status` (never called; the dashboard buckets runs itself), the `scaffold_health` Stage 0 infrastructure probe (superseded by real activities), and the unused `RunStatus` union in the frontend.

**Fresh-setup verification, and a real bug it caught.** A clean checkout was made with `git archive`, installed from the lockfile, and tested. `uv sync --locked` resolved cleanly and 73 tests passed with 23 correctly skipped, which confirms the lockfile is complete. `.env.example` was audited against `app/config.py`: every setting the code reads is documented.

That run also exposed a genuine defect. On a cold machine the first workflow test downloads the Temporal test-server binary — 33 seconds versus 3.5 afterwards — and the `wait_until` test helper only allowed a 5-second budget, so it failed spuriously. Anyone running the suite for the first time, including a grader, would have seen a red test on a healthy codebase. Both polling helpers now use a generous wall-clock budget and still return as soon as their predicate holds.

**Documentation.** `README.md` was rewritten as a submission document: what the system is and why Temporal is the right tool, quick start, provider selection, how the wake policy, agent contract, approval gate, lifecycle authority, memory, persistence, and Continue-As-New actually work, the full API table, templates, the worker-restart procedure, how to run the tests, the repository layout, and an explicit list of known tradeoffs. `docs/DEMO.md` is new: a nine-step walkthrough with what to say at each step, a recording checklist, and a troubleshooting table. `docs/ARCHITECTURE.md` gained a closing section defending the design decisions and naming what would come next.

### Validation performed (2026-09-10)

| Check | Result |
| --- | --- |
| Backend `pytest` with `RUN_INTEGRATION=1` | PASS: 96 passed, 0 skipped |
| Fresh checkout: `uv sync --locked` then `pytest` | PASS: 73 passed, 23 skipped |
| Backend `ruff check` / `ruff format --check` / `mypy` strict | PASS |
| `alembic upgrade head` and `alembic check` | PASS: no drift |
| Frontend `npm run lint` / `typecheck` / `build` | PASS |
| End-to-end regression against the running stack | PASS: 10 of 10 |
| Browser check of every screen | PASS, including 400px with no overflow and no console errors |

The end-to-end regression ran against the full stack with the live OpenRouter provider and covered every path the demo relies on: Happy Path completing through a terminal event; Delivery Crisis escalating to `message_logistics_team`; routine events handled without waking the agent; terminate ending a sleeping run; the approval gate holding `message_customer` while non-gated actions still execute; a rejected action never executing; an approved action executing; analytics reporting approvals and customer actions; the three templates; and HTTP errors mapping to 404, 409, and 422.

One assertion in that harness was initially too strict — it expected zero executed actions while an approval was pending, but the live agent also proposed a non-gated internal note, which correctly executes. The check now asserts that the *gated* action specifically has not run.

### Final state

- 96 backend tests; strict mypy over 33 source files; zero lint errors.
- Frontend builds clean; one known non-blocking PostCSS anonymous-default-export warning.
- Four migrations, no schema drift.
- Runs on the deterministic mock with no API key, or on a real model via OpenRouter or Anthropic.

### Known limitations

Carried forward deliberately, and documented in the README:

- Business actions are simulated.
- Only the OpenRouter provider has been exercised against a live API; the Anthropic path is type-checked but unrun.
- Memory compaction is deterministic truncation, not summarization.
- The UI polls every two seconds rather than streaming.
- No authentication, and no pagination on the dashboard or supervisor list.
- The classifier has no caching, so a burst of customer messages means a burst of calls.
- Analytics are per-run; there is no cross-run or per-supervisor view.
- Approvals live in workflow state, so there is no cross-run approval queue, and they never time out.
- Supervisors cannot be edited after creation; templates are read-only presets in code.
- Continue-As-New carries the last 50 seen event ids, so a very old duplicate arriving after several continuations would be reprocessed.
- The Temporal dev container runs as root to work around a root-owned named volume. Local development only.
- `ORDER_PILOT_STAGED_BUILD_PROMPT.md` remains in already-pushed Git history.

### Files and areas changed in Stage 7

- Added: `docs/DEMO.md`.
- Rewritten: `README.md`.
- Modified: `docs/ARCHITECTURE.md` (tradeoffs section), `.gitignore`, `backend/app/agent/schema.py`, `backend/app/repository.py`, `backend/app/temporal/worker.py`, `backend/tests/test_workflow.py`, `backend/tests/test_end_to_end.py`, `frontend/lib/types.ts`, this file.
- Untracked: `ORDER_PILOT_STAGED_BUILD_PROMPT.md`.

### Stage history

| Stage | Delivered |
| --- | --- |
| 0 | Scaffold, configuration, schema, Temporal connection |
| 1 | `OrderSupervisorWorkflow`: Signals, Queries, durable timers, lifecycle rules |
| 2 | Agent runtime: validated decisions, providers, five actions, memory |
| 3 | Persistence and the FastAPI control plane |
| 4 | Operations UI and event simulator — P0 complete |
| 5 | Hybrid wake classifier, approval gate, durability demo — P1 complete |
| 6 | Analytics, adaptive guidance, Continue-As-New, templates — P2 complete |
| 7 | Hardening, fresh-setup verification, documentation, demo script |

**All stages are complete. No further stage is planned.**
