# Project status

## Stage 6 — complete (2026-09-10). P0, P1, and P2 are done.

Stage 5 was committed and pushed by the user as `c62a484`, together with the OpenRouter provider work. Stage 6 adds P2: run analytics, adaptive wake guidance, Continue-As-New, and supervisor templates. No commit or push has been made by the assistant.

### Built in Stage 6

**Run analytics.** `GET /api/runs/{run_id}/analytics` returns events received, agent wake-ups, no-wake events, classifier calls, scheduled reviews, actions executed, customer actions, approvals granted and rejected, continuations, and duration, plus two derived ratios: wake rate and actions per wake. Counters are maintained by the workflow and persisted with each snapshot, so analytics are derived from the run row rather than kept as a second aggregate that could drift. Wake rate counts only signal-driven wakes, since the start wake and scheduled reviews are not responses to events.

**Adaptive wake guidance.** The agent may return up to three short standing hints. They are cleaned, de-duplicated, length-capped, persisted on the run (migration `0003`), shown in the control room, and fed to the classifier on later ambiguous events. Guidance is advisory only: it cannot widen the action allow-list or lower the supervisor's wake threshold, and there is a test for exactly that.

**Supervisor templates.** Standard, VIP/High-Touch, and Cost-Conscious, exposed at `GET /api/supervisors/templates` and loadable into the supervisor form. They differ in ways that show up in behaviour, not just labels: VIP wakes on everything and reviews every 20 minutes with no approval gate; Cost-Conscious wakes only on critical events, reviews every four hours, and cannot message the customer at all; Standard sits between them and holds customer contact for a human.

**Continue-As-New.** Configurable per supervisor with `continue_as_new_after_events` (0 disables it, low values make it easy to demonstrate). The continuation carries only compact state and preserves order ID, run ID, and workflow ID, so it remains one logical run. It happens only at a quiet point: no queued events, no approved actions waiting, nothing pending a human, not paused, not terminal.

New counters: `customer_actions`, `continuations`.

### Two real bugs found and fixed

1. **Events were dropped at the Continue-As-New boundary.** The carried state hard-coded `pending_events=[]`, and the persist call inside the continuation awaits, which yields and lets Signal handlers run — so an event arriving in that window was lost silently. The full-suite run caught it by timing: `delivered` vanished and the run reported two events instead of three. Queued events are now carried across. The seen-event-id tail was also being taken with `sorted(...)[-50:]`, which is lexicographic rather than chronological; the id store is now insertion-ordered so the carried tail is genuinely the most recent.
2. **`completion_recommended` defaulted to `True`.** It has been wrong since Stage 2 (`de895af`) and I reported it as `False` at the time. It could not end a run — the workflow owns lifecycle, which is precisely why that separation matters — but any decision omitting the field would have falsely displayed "the agent recommended completion" to an operator. Now `False`, with a comment explaining that the absence of an opinion is not a recommendation.

To make the first one testable rather than timing-dependent, the carried-state construction was extracted into a pure `_carried_state()` method and covered by a direct round-trip test against `_restore()`.

### Validation performed (2026-09-10)

| Check | Result |
| --- | --- |
| Backend `pytest` with `RUN_INTEGRATION=1` | PASS: 96 passed, 0 skipped (run twice, stable) |
| `pytest tests/test_p2.py` | PASS: 12 P2 tests (run three times, stable) |
| Backend `ruff check` / `ruff format --check` / `mypy` strict | PASS |
| `alembic upgrade head` and `alembic check` | PASS: no drift |
| Frontend `npm run lint` / `typecheck` / `build` | PASS |
| Live end-to-end run on OpenRouter with a low CAN threshold | PASS: see below |
| Browser check of the P2 UI | PASS: no console or page errors |

P2 tests cover: the three templates differing in wake sensitivity, review interval, allowed actions, and approval policy; templates referencing only real actions; guidance bounding, de-duplication, and length capping; guidance defaulting to empty and `completion_recommended` defaulting to false; guidance being recorded and reaching the classifier; guidance not widening the allow-list; Continue-As-New preserving state and identity; a continuation not re-running the start wake; a pending approval blocking a continuation until it is settled; Continue-As-New being off by default; the carried-state round trip losing nothing; and every event surviving a run that continues.

The live run used a VIP supervisor at `continue_as_new_after_events=2` against `anthropic/claude-sonnet-4.5`. It continued once mid-run with order state, memory, and counters intact; the agent generated three real guidance lines of its own ("Treat any delivery date risk as HIGH priority due to VIP status"); the run completed with 3 events, 4 wake-ups, 7 executed actions, 2 customer actions, 1 continuation, a 100% wake rate (correct for a HIGH-sensitivity supervisor), and 1.75 actions per wake. The persisted timeline held 31 rows across the continuation boundary, including `RUN_CONTINUED` and `WAKE_GUIDANCE_UPDATED`.

### Known limitations

- Only the OpenRouter provider has been exercised live; `ClaudeProvider` remains type-checked but unproven at runtime.
- Analytics are per-run. There is no cross-run or per-supervisor aggregate view, which is what a real operations team would want next.
- Guidance is replaced wholesale by each decision that emits it, rather than merged or aged out, so a later decision can quietly drop an earlier hint.
- Continue-As-New carries the last 50 seen event ids. An extremely old duplicate arriving after several continuations would be reprocessed.
- Templates are read-only presets in code. They cannot be edited or added through the UI, and existing supervisors cannot be edited at all.
- The classifier still has no caching, and each ambiguous event costs a call.
- No authentication anywhere; no pagination on the dashboard or supervisor list.

### Files and areas changed

- Added: `backend/app/domain/templates.py`, `backend/migrations/versions/0003_wake_guidance.py`, `backend/tests/test_p2.py`.
- Modified (backend): `app/agent/schema.py` (guidance field, `clean_guidance`, `completion_recommended` fix), `app/agent/prompt.py`, `app/temporal/activities.py` (guidance through the decision and snapshot contracts), `app/temporal/workflow.py` (guidance handling, Continue-As-New, `_carried_state`, ordered event ids, customer-action counter), `app/temporal/types.py` (`CarriedState`, CAN threshold), `app/models.py`, `app/repository.py`, `app/services/runs.py`, `app/api/schemas.py`, `app/api/runs.py` (analytics endpoint), `app/api/supervisors.py` (templates endpoint), `tests/test_api.py`.
- Modified (frontend): `lib/types.ts`, `lib/api.ts`, `components/run-cards.tsx` (analytics and guidance cards), `app/runs/[runId]/page.tsx`, `app/supervisors/page.tsx` (template picker, CAN threshold).
- Modified (docs): `README.md`, `docs/ARCHITECTURE.md`, this file.

### Next stage

Stage 7 — Final hardening and submission readiness: full regression pass, remove dead code, verify a fresh setup from a clean clone, finalise the demo script and walkthrough checklist, and complete the documentation of workflow-versus-activity responsibilities, signals, queries, timers, memory, wake policy, approvals, and Continue-As-New.

**Stage 7 has NOT been started.**
