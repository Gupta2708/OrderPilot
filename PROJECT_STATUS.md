# Project status

## Stage 5 — complete (2026-09-10). P0 and P1 are done.

Stage 4 was committed and pushed by the user as `f799214`. Stage 5 adds the P1 layer: a hybrid wake policy, a human approval gate, and a demonstrated durability story. No commit or push has been made by the assistant.

### Built in Stage 5

**Hybrid wake policy.** `evaluate_fast_path` answers only for known lifecycle events and returns `None` for the two cases a table cannot honestly judge: an unrecognised event type, and a customer message. Those go to `classify_event`, a new Activity that asks the provider for a small validated verdict (`wake_now`, `severity`, `category`, `reason`). The classifier never gets the last word: its severity is capped by the supervisor's wake sensitivity, and any failure falls back to deterministic evaluation. Every verdict is recorded with the rule that produced it — `deterministic_severity_table`, `ai_classifier:<provider>`, or `classifier_fallback_deterministic`.

**Human approval gate.** Supervisors carry `require_approval_for`, defaulting to `message_customer`. A gated action is proposed but held: the workflow records `ACTION_PENDING_APPROVAL`, reports `AWAITING_APPROVAL`, and executes nothing. `approve_action` and `reject_action` Signals settle it; approved actions are queued and executed by the run loop rather than inside the Signal handler, so execution stays on the deterministic path. There is no code path from a rejection to an execution.

**API and UI.** New endpoints `POST /api/runs/{run_id}/approvals/{approval_id}/approve` and `.../reject`. The supervisor form configures the approval policy, the control room shows an approvals card with Approve and Reject, and the status badge shows `AWAITING_APPROVAL`.

**Durability.** No new mechanism was needed — state already lives in Temporal — so this stage adds the demonstration: a documented manual procedure in the README and an automated test that leaves the task queue genuinely unattended.

New counters: `classifier_calls`, `approvals_granted`, `approvals_denied`.

**One real bug found and fixed.** Signals with two arguments were being sent positionally, which the SDK rejects; `reject_action` (approval id plus reason) was the first two-argument Signal in the system, so nothing had caught it. The service now always uses the explicit `args` list form.

### Validation performed (2026-09-10)

| Check | Result |
| --- | --- |
| Backend `pytest` with `RUN_INTEGRATION=1` | PASS: 79 passed, 0 skipped |
| `pytest tests/test_p1.py` | PASS: 11 P1 tests |
| Backend `ruff check` / `ruff format --check` / `mypy` strict | PASS |
| Frontend `npm run lint` / `typecheck` / `build` | PASS |
| Headless-browser P1 walkthrough | PASS: 8 of 8, no console or page errors |

P1 tests cover: routine events never reaching the classifier; ambiguous and unknown events deferring to it; sensitivity still governing the verdict; a broken classifier falling back to deterministic rules while still escalating unknown events; an over-eager classifier being capped by sensitivity; the classifier waking the agent for a risky customer message and declining for a routine one; a sensitive action waiting for approval and then executing once approved; a rejected action never executing; non-sensitive actions still executing directly; and the run surviving a worker restart.

The durability test runs against a real local dev server rather than the time-skipping one, because it deliberately leaves the task queue unattended and the time-skipping server cannot represent that — it waits for workflow progress. The test starts a run, shuts the worker down completely, sends an event into that gap, starts a fresh worker, and asserts the run picks the event up with memory and history intact before completing normally.

The browser walkthrough drove the real stack and confirmed: the approval policy is configurable and shown; a routine event is handled without waking the agent; a customer message is classified (`rule = ai_classifier:mock`); the run reports `AWAITING_APPROVAL` with the action held and `Actions = 0`; rejecting records `ACTION_DENIED` and executes nothing; approving executes the action; and an unknown event type is escalated rather than dropped.

### Live provider verified (2026-09-10, after Stage 5)

The user supplied an OpenRouter key rather than an Anthropic one, so an `OpenRouterProvider` was added alongside `ClaudeProvider`. OpenRouter is OpenAI-compatible, so it uses the OpenAI SDK against `https://openrouter.ai/api/v1`; the workflow, approval gate, and classifier were unchanged, because the provider interface already isolated them. `ClaudeProvider` is retained for an `sk-ant-` key.

**The long-standing "never run against a live API" limitation is now closed.** A full run was driven through the HTTP API against `anthropic/claude-sonnet-4.5`: the start wake produced a real `NO_ACTION` with reasoning; `payment_confirmed` was absorbed by the deterministic fast path without waking the agent; `shipment_delayed` woke it, and it followed the live run instruction, escalating to logistics and writing an internal note; the customer message it drafted was held by the approval gate with its real text visible; approving it executed the send; and `delivered` completed the run with a model-written memory summary and final output.

Three real defects were found and fixed by running against a live model:

1. **Actions came back with empty arguments.** `arguments` was a free-form `dict[str, Any]`, which under a strict JSON schema reliably produced `{}`. The agent could choose an action but never actually say anything, and the executor's safe defaults masked it as generic canned text. Fixed by giving arguments an explicit schema with described `message` and `note` fields.
2. **A persistence failure wedged the whole run.** `persist_snapshot` failures propagated and stalled the workflow loop. Since Temporal owns execution truth and Postgres only mirrors it, persistence failures are now counted and non-fatal, with the buffered rows retried at the next flush — plus a flag that stops unflushed rows from re-waking the loop, which would otherwise spin.
3. **The test suite was reading the developer's `.env`** and making real paid API calls, which is why it slowed from 9s to 185s once a key was configured. `tests/conftest.py` now forces the mock provider and strips provider keys, so tests never depend on local configuration and never cost money.

### Known limitations

- The classifier is called per ambiguous event with no caching, so a burst of customer messages means a burst of calls — and now those cost money.
- Only the OpenRouter path has been exercised live. `ClaudeProvider` remains type-checked but unproven at runtime, since no Anthropic key is available.
- Live runs are slower than the mock: a decision takes seconds, so a run briefly shows `ACTING` where the mock was instant. Any demo script needs to poll rather than sleep for a fixed second.
- Approvals live in workflow state and the timeline, not in their own table, so there is no cross-run "approval queue" view. Adequate for one order at a time; a real operations tool would want a queue.
- Approvals have no timeout: a gated action waits indefinitely until someone decides or the run's maximum age ends it.
- Rejecting from the UI sends a fixed reason. A free-text reason would be better.
- Adaptive wake guidance is accepted by the classifier prompt but nothing generates it yet; that is Stage 6, along with analytics, Continue-As-New, and supervisor templates.

### Files and areas changed

- Added: `backend/tests/test_p1.py`, `frontend` approvals card (in `components/run-cards.tsx`).
- Modified (backend): `app/domain/wake_policy.py` (fast path, `needs_classification`, `meets_threshold`), `app/domain/lifecycle.py` (`AWAITING_APPROVAL`), `app/agent/schema.py` (`WakeClassification`), `app/agent/prompt.py` (classifier prompt), `app/agent/provider.py` (`classify` on both providers), `app/temporal/activities.py` (`classify_event`), `app/temporal/workflow.py` (hybrid wake, approval gate, approve/reject Signals, counters), `app/temporal/types.py`, `app/services/runs.py` (approve/reject, two-argument Signal fix), `app/api/schemas.py`, `app/api/supervisors.py`, `app/api/runs.py`, `tests/test_api.py`.
- Modified (frontend): `lib/types.ts`, `lib/api.ts`, `components/run-cards.tsx`, `app/runs/[runId]/page.tsx`, `app/supervisors/page.tsx`.
- Modified (docs): `README.md`, `docs/ARCHITECTURE.md`, `.env.example`, this file.

Live-provider work (after Stage 5): added `OpenRouterProvider` and `_extract_json` in `app/agent/provider.py`, `ActionArguments` in `app/agent/schema.py`, OpenRouter settings in `app/config.py`, the `openai` dependency in `pyproject.toml`/`uv.lock`, `tests/conftest.py`, non-fatal persistence plus the `_persist_blocked` guard and `persist_failures` counter in `app/temporal/workflow.py`, and a resilience test in `tests/test_p1.py`.

### Next stage

Stage 6 — P2: run analytics; adaptive agent-generated wake guidance that is validated, persisted, and safely consumed by the classifier; Continue-As-New with a configurable low development threshold; and the Standard, VIP/High-Touch, and Cost-Conscious supervisor templates.

**Stage 6 has NOT been started.**
