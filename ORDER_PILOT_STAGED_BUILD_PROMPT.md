# Order Supervisor — Staged Build Prompt for Codex / Claude Code

## Role

You are the senior full-stack + AI systems engineer responsible for implementing this assignment end-to-end.

Build a **small, reliable, technically strong POC** for a long-running AI Order Supervisor. The important engineering story is not "a chatbot for orders"; it is a **durable, event-driven AI supervisor whose lifecycle is owned by Temporal**.

You must work in **major stages**. Do **not** implement the entire project in one pass.

---

# 0. Source of Truth

Before changing code:

1. Read the attached **Order Supervisor assignment PDF** completely.
2. Read this file completely.
3. Inspect the existing repository before deciding structure or dependencies.
4. If the repository already contains working code, preserve it where reasonable and avoid unnecessary rewrites.
5. The assignment PDF is authoritative for required functionality.
6. This file adds implementation guidance and P1/P2 enhancements but must never weaken an assignment requirement.

If there is a conflict:
- Assignment requirement wins.
- Then choose the smallest reliable implementation.

---

# 1. Product Goal

Build **Order Supervisor**, a durable AI operations control tower that supervises one order from creation until a workflow-owned terminal condition.

For each order:

- Start exactly one long-running Temporal Workflow.
- Receive lifecycle events as Temporal Signals.
- Wake the main agent on:
  1. workflow start,
  2. important incoming events,
  3. scheduled wake-up.
- Let unimportant events update state without unnecessarily invoking the main agent.
- Let the agent take structured business actions.
- Maintain compact memory + an auditable activity timeline.
- Let the workflow sleep durably instead of polling in a tight loop.
- Allow live run-specific instructions.
- Support pause, resume, interrupt/terminate behavior.
- Produce final summary, important actions, learnings, and recommendations.
- Completion must be controlled by workflow lifecycle rules, not arbitrary LLM output.

The final demo should make the evaluator immediately understand **why Temporal is being used**.

---

# 2. Required Stack

Use the assignment stack:

- Frontend: Next.js with App Router
- UI: Tailwind CSS
- Backend: Python + FastAPI
- Orchestration: Temporal Python SDK (`temporalio`)
- Persistence: PostgreSQL (local Docker Postgres or Supabase is acceptable)
- LLM/tool orchestration: one simple provider abstraction of your choice

Important:
- Do not add microservices, Kafka, vector DBs, Kubernetes, multi-agent frameworks, or other unnecessary infrastructure.
- Prefer boring, understandable code.
- Do not perform network/API calls directly from Temporal Workflow code. Put LLM calls, database writes, and other side effects in Activities.
- Temporal Workflow code should remain replay-safe/deterministic.
- Use Signals for asynchronous state-changing events.
- Use Queries where useful for reading current Workflow state.
- Use durable Temporal timers/waits for sleeping.
- Use Continue-As-New only in the P2 stage.

---

# 3. Architecture Target

Aim for this separation:

```text
Next.js UI
   |
   v
FastAPI control plane
   |
   +----------------------> PostgreSQL
   |
   v
Temporal Client
   |
   v
OrderSupervisorWorkflow  <--- signals / timers / workflow state
   |
   +--> Agent Activity ------> LLM
   |
   +--> Business Action Activities
   |
   +--> Persistence / Memory Activities
```

Responsibilities:

### Temporal Workflow
Own:
- order lifecycle,
- pending event handling,
- pause/resume state,
- next wake-up,
- terminal/completion rules,
- current high-level workflow state.

### Activities
Own:
- LLM inference,
- business action execution,
- DB writes,
- memory compaction,
- final summary generation,
- other non-deterministic work.

### FastAPI
Own:
- supervisor CRUD,
- run creation/list/detail,
- event injection,
- instruction injection,
- pause/resume/terminate controls,
- API consumed by frontend.

### PostgreSQL
Own the product-facing persistent record:
- supervisor configurations,
- runs,
- unified activity history,
- compact memory,
- final outputs.

### Next.js
Own:
- dashboard,
- supervisor configuration,
- start-run flow,
- run control room,
- event simulator,
- instructions,
- status/timeline/memory display,
- analytics.

---

# 4. Core Domain Model

Keep schema small.

## supervisors

Suggested fields:

```text
id
name
description
base_instruction
allowed_actions
wake_aggressiveness
default_wake_minutes
model_config
created_at
updated_at
```

## runs

Suggested fields:

```text
id
order_id
supervisor_id
temporal_workflow_id
status
order_status
order_state JSONB
memory_summary
next_wake_at
last_wake_at
run_instructions JSONB/text
latest_decision JSONB
final_summary
learnings
recommendations
created_at
updated_at
completed_at
```

## activities

Use one unified append-only activity table:

```text
id
run_id
type
subtype
source
severity
payload JSONB
created_at
```

Useful activity types:

```text
EVENT_RECEIVED
WAKE_DECISION
AGENT_DECISION
ACTION_EXECUTED
ACTION_PENDING_APPROVAL
ACTION_APPROVED
ACTION_REJECTED
MEMORY_UPDATED
SLEEP_SCHEDULED
INSTRUCTION_ADDED
RUN_PAUSED
RUN_RESUMED
RUN_TERMINATED
RUN_COMPLETED
FINAL_OUTPUT
UNKNOWN_EVENT
```

Do not create many additional tables unless a later feature truly requires one.

---

# 5. Required Business Actions

Implement the exact five assignment actions:

```text
message_fulfillment_team
message_payments_team
message_logistics_team
message_customer
create_internal_note
```

They may be simulated.

Each execution must:
- validate input,
- create an activity record,
- return structured success/failure output,
- be visible in the run timeline.

Do not integrate real Slack/email/SMS/commerce systems.

---

# 6. Agent Runtime Contract

The main agent must return **structured output**, never free-form control logic.

Use a schema conceptually similar to:

```json
{
  "decision": "ACT | SLEEP | NO_ACTION",
  "priority": "LOW | MEDIUM | HIGH | CRITICAL",
  "reason_summary": "short auditable explanation",
  "actions": [
    {
      "tool": "message_logistics_team",
      "arguments": {}
    }
  ],
  "memory_update": "compact factual update",
  "sleep": {
    "mode": "duration | timestamp",
    "minutes": 30,
    "wake_at": null
  },
  "wake_guidance": null,
  "completion_recommended": false
}
```

Rules:
- Validate all model output with Pydantic.
- Never execute arbitrary tool names.
- Only execute actions allowed by the selected supervisor configuration.
- Store a concise **reason summary**, not hidden chain-of-thought.
- The LLM may recommend completion but cannot own the terminal lifecycle transition.
- If structured output fails validation, retry safely once or use a deterministic fallback.

Support:
- one real LLM provider,
- plus a deterministic mock/fake provider so the project can still be demonstrated without a paid API key.

Do not build several provider integrations.

---

# 7. Wake Policy

Implement a hybrid wake system.

## Level A — deterministic fast path

Examples that normally wake immediately:
- `payment_failed`
- `shipment_delayed`
- `refund_requested`
- significant `customer_message_received`

Examples that may simply update state:
- `payment_confirmed`
- normal `shipment_created`

Do not blindly hardcode every possible business decision. The rule layer is only a cheap fast path.

## Level B — lightweight classifier

For ambiguous or unknown events, use a lightweight structured classifier/policy:

```json
{
  "wake_now": true,
  "severity": "HIGH",
  "category": "customer_risk",
  "reason": "Customer is threatening cancellation."
}
```

The classifier should be able to consume evolving wake guidance added in P2.

Every wake/no-wake decision should be visible in the unified activity timeline.

---

# 8. Workflow State

The workflow should maintain state conceptually like:

```text
run_id
order_id
status
paused
terminated
terminal
pending_events
order_state
memory_summary
run_instructions
latest_decision
next_wake_at
wake_guidance
event_count
```

Model the order state explicitly instead of relying only on natural-language memory.

Suggested order state:

```json
{
  "payment": {"status": "pending"},
  "fulfillment": {"status": "not_started"},
  "shipment": {"status": "not_created"},
  "delivery": {"status": "pending"},
  "refund": {"status": "none"},
  "customer": {"last_message": null}
}
```

The agent context should include only useful information:

```text
base supervisor instruction
+ live run-specific instructions
+ current structured order state
+ compact memory summary
+ triggering/latest event
+ a small recent activity window
+ allowed actions
```

Do not dump the entire raw history into every prompt.

---

# 9. Completion Rules

The workflow must end through explicit lifecycle rules such as:

- terminal `delivered` event,
- a clearly defined terminal refund/cancellation condition if implemented,
- manual terminate,
- configured maximum workflow age,
- another explicit deterministic completion rule.

Do not let:

```text
LLM says "close workflow"
```

be the only completion mechanism.

At completion, run a finalization Activity that generates:

- final summary,
- important actions,
- key learnings,
- feedback/recommendations,
- basic run statistics.

Persist these and display them in the UI.

---

# 10. UI Product Direction

The UI should feel like a compact **AI operations control room**, not a chatbot.

Keep styling professional but do not spend disproportionate time on visual polish.

## Dashboard

Show:
- active runs,
- sleeping runs,
- attention-required runs,
- completed runs,
- run table/cards,
- state badges.

Useful states:

```text
ACTING
SLEEPING
ATTENTION
PAUSED
AWAITING_APPROVAL
COMPLETED
TERMINATED
```

## Supervisor Configuration

Configure:
- name,
- base instruction,
- available actions,
- default wake behavior,
- wake sensitivity/aggressiveness,
- optional model config,
- optional approval policy.

## Start Run

Allow:
- order ID,
- useful order metadata/context,
- supervisor template,
- initial per-run instruction/context.

## Run Control Room

This is the main screen.

Show:
- order identity,
- current workflow state,
- Temporal/workflow status,
- acting/sleeping/paused status,
- countdown/next wake,
- structured order state,
- compact memory,
- latest agent decision,
- wake decision,
- unified timeline,
- tool/action history,
- pending approvals,
- event injector,
- run-specific instruction input,
- pause/resume/terminate controls,
- final output after completion.

Avoid exposing raw chain-of-thought.

## Event Simulator

Support direct event injection and scenario presets.

At minimum:

### Happy Path
```text
order_created
payment_confirmed
shipment_created
delivered
```

### Payment Trouble
```text
order_created
payment_failed
payment_confirmed
shipment_created
delivered
```

### Delivery Crisis
```text
order_created
payment_confirmed
shipment_created
shipment_delayed
customer_message_received
delivered
```

### Refund Risk
```text
order_created
payment_confirmed
shipment_created
customer_message_received
refund_requested
```

Provide a simple `Run next event` flow. Auto-simulation is optional if reliable.

---

# 11. P1 Features

After all P0 acceptance requirements work, add:

1. Hybrid rule + lightweight AI wake classifier.
2. Human approval gate for sensitive actions, especially `message_customer`.
3. Unknown-event classification/escalation.
4. Strong scenario simulator presets.
5. Visible decision cards:
   - why supervisor woke,
   - what it decided,
   - what it did,
   - when it will wake next.
6. Worker-restart durability demonstration/documentation.
7. Better memory compaction if needed.

Do not make approval an entirely separate agent.

---

# 12. P2 Features

After P1 is stable, add:

1. Run analytics:
   - events received,
   - main agent wake-ups,
   - no-wake events,
   - actions executed,
   - customer actions,
   - scheduled wake-ups,
   - approvals/rejections,
   - run duration.

2. Adaptive agent-generated wake guidance.
   - validate it,
   - persist it,
   - let classifier consume it safely.

3. Temporal `Continue-As-New`:
   - preserve only compact essential state,
   - keep logical order/workflow identity coherent,
   - make threshold configurable,
   - make testing easy with a low development threshold.

4. Multiple supervisor templates:
   - Standard Order Supervisor,
   - VIP / High-Touch Supervisor,
   - Cost-Conscious Supervisor.

5. Tests covering important lifecycle and failure cases.

Do not add unrelated P3 features.

---

# 13. Engineering Quality Requirements

Throughout the project:

- Use typed schemas.
- Add meaningful error handling.
- Use clear domain names.
- Keep Temporal-specific code isolated.
- Keep business logic testable outside HTTP handlers.
- Use environment variables and provide `.env.example`.
- Never commit real API keys/secrets.
- Provide deterministic seeded/mock demo data where useful.
- Make all status transitions explicit.
- Prefer append-only timeline records.
- Avoid duplicate event processing where practical.
- Ensure terminal workflows do not keep scheduling wakes.
- Ensure paused workflows do not execute normal agent actions until resumed.
- Ensure terminate works even while sleeping.
- Ensure live instructions affect subsequent agent decisions.
- Make the app runnable from fresh setup instructions.
- Before choosing package versions or SDK calls, inspect current official docs/package metadata available to you. Do not invent obsolete APIs.

---

# 14. Mandatory Staged Execution Protocol

You must work through the stages below **one stage at a time**.

## At the beginning of every stage

1. Inspect current repository state.
2. Read this file, the assignment, and `PROJECT_STATUS.md` if it exists.
3. Check what was actually completed previously.
4. Do not assume a feature works because a previous message says it works.
5. Run the smallest relevant sanity checks.
6. Implement only the current stage.

## During a stage

- Modify all files legitimately required for that stage.
- Fix issues directly caused by the stage.
- Do not opportunistically implement future stages.
- Do not broadly restructure working code without need.
- Add tests for important logic.
- Keep the application runnable.

## At the end of every stage

You MUST:

1. Run relevant tests.
2. Run lint/type/build checks.
3. Run a smoke test where practical.
4. Review the diff for accidental changes.
5. Update/create `PROJECT_STATUS.md`.
6. **Do not run `git commit`.**
7. **Do not run `git push`.**
8. **Do not start the next stage.**
9. Stop and report.

Use this exact completion format:

```text
STAGE <N> COMPLETE — <name>

Built
- ...

Validation
- command: <...> -> PASS/FAIL

Manual verification
- ...

Files / areas changed
- ...

Known limitations
- ...

PROJECT_STATUS.md
- Updated: yes

Suggested commit message
<type(scope): concise commit message>

Run manually
git status
git add .
git commit -m "<same commit message>"
git push

NEXT STAGE
Stage <N+1> — <name>

I have NOT started the next stage.
Reply CONTINUE to begin Stage <N+1>.
```

If a test fails:
- attempt reasonable fixes within the current stage,
- never claim PASS when it failed,
- document the remaining issue,
- still stop instead of spilling into the next stage.

---

# 15. Major Build Stages

## STAGE 0 — Repository Audit + Architecture + Scaffold

Goal: establish a clean foundation without overbuilding.

Do:
- inspect repository,
- preserve useful existing work,
- establish frontend/backend layout,
- set up environment/config conventions,
- configure Postgres access,
- configure Temporal local-development path,
- create FastAPI base app,
- create Next.js/Tailwind base app if absent,
- create Temporal client/worker skeleton,
- create minimal DB models/migrations,
- create `.env.example`,
- create/update README quick-start skeleton,
- create `PROJECT_STATUS.md`,
- add a short architecture note/diagram in Markdown.

Do not build the actual full workflow yet.

Exit gate:
- backend starts,
- frontend starts,
- DB connectivity path is defined/testable,
- Temporal worker/client scaffolding imports/runs,
- structure is understandable.

Then STOP.

---

## STAGE 1 — Durable Temporal Workflow Core

Goal: prove the heart of the assignment.

Implement:
- exactly one workflow ID per order,
- `OrderSupervisorWorkflow`,
- initial workflow state,
- order-event Signal,
- run-specific-instruction Signal,
- pause Signal,
- resume Signal,
- terminate Signal,
- useful Query for current state,
- pending-event handling,
- durable scheduled wake-up,
- wake on workflow start,
- wake on important signal,
- wake on timer,
- deterministic lifecycle/terminal rules,
- initial deterministic/simple wake policy,
- no tight polling loop.

Add tests for:
- workflow start,
- signal reception,
- sleep/wake,
- pause/resume,
- terminate,
- terminal event completion.

No full LLM orchestration yet; use a deterministic placeholder decision if required.

Exit gate:
Temporal behavior is demonstrably correct before adding AI complexity.

Then STOP.

---

## STAGE 2 — Agent Runtime + Actions + Memory

Goal: turn the durable workflow into an AI supervisor.

Implement:
- Pydantic structured agent-decision schema,
- one real LLM provider abstraction,
- deterministic mock provider,
- LLM inference in Activities, not Workflow code,
- exact five required business actions,
- action allow-list enforcement,
- concise reason summaries,
- structured order-state updates,
- compact rolling memory,
- memory-compaction Activity,
- safe fallback for malformed model output,
- next-wake instructions from agent,
- finalization Activity,
- lifecycle remains workflow-owned.

Add focused tests for:
- schema validation,
- action allow-list,
- malformed model output,
- memory compaction,
- lifecycle authority.

Exit gate:
A Temporal run can wake, invoke the agent Activity, execute simulated actions, update memory, and sleep again.

Then STOP.

---

## STAGE 3 — Persistence + FastAPI + End-to-End P0 Backend

Goal: make the system usable by the UI.

Persist:
- supervisors,
- runs,
- unified activities,
- order state,
- memory,
- latest decision,
- final outputs.

Implement API surface:

```text
POST   /api/supervisors
GET    /api/supervisors
GET    /api/supervisors/{id}

POST   /api/runs
GET    /api/runs
GET    /api/runs/{run_id}

POST   /api/runs/{run_id}/events
POST   /api/runs/{run_id}/instructions

POST   /api/runs/{run_id}/pause
POST   /api/runs/{run_id}/resume
POST   /api/runs/{run_id}/terminate

GET    /api/runs/{run_id}/state
```

Requirements:
- starting run starts Temporal Workflow,
- event endpoint Signals it,
- instructions Signal it,
- controls map safely to workflow operations,
- API exposes timeline/memory/final output,
- actions are persisted as activity records,
- sensible HTTP errors,
- basic duplicate protection where practical.

Exit gate:
Full P0 backend can be exercised without frontend.

Then STOP.

---

## STAGE 4 — Product UI + Event Simulator + Complete P0

Goal: satisfy all assignment P0 acceptance criteria from the browser.

Build:
- dashboard,
- supervisor list/configuration,
- start-run screen,
- active/completed run list,
- Run Control Room,
- status badges,
- structured order-state card,
- current sleep/next-wake display,
- memory card,
- latest-decision/wake-reason card,
- unified timeline,
- action history,
- event injector,
- run-specific instruction input,
- pause/resume/terminate controls,
- final summary/learnings/recommendations,
- scenario presets: Happy Path, Payment Trouble, Delivery Crisis, Refund Risk.

Keep UI clear, modern, and restrained.

Exit gate:
All assignment acceptance criteria can be demonstrated from the browser.

Then STOP.

---

## STAGE 5 — P1: Smarter Wake Policy + Human Approval + Resilience

Goal: make the POC feel like a credible autonomous operations product.

Implement:
- deterministic fast-path wake rules,
- lightweight structured AI classifier for ambiguous/unknown events,
- wake/no-wake audit records,
- unknown-event escalation,
- human approval gate for sensitive actions,
- configurable approval requirement for `message_customer`,
- approve/reject backend + UI,
- pending-approval state,
- decision cards showing trigger/reason/action/next review,
- stronger scenario simulator behavior,
- worker-restart durability demo path/documentation,
- memory improvements if needed.

Test:
- unimportant event avoids main agent,
- high-priority event wakes it,
- unknown event handled safely,
- customer message can require approval,
- rejection does not execute action,
- workflow continues correctly after worker restart.

Exit gate:
P1 demo is reliable.

Then STOP.

---

## STAGE 6 — P2: Analytics + Adaptive Wake Guidance + Continue-As-New + Templates

Goal: add advanced but relevant system/product features.

Implement analytics:
- events received,
- agent wake-ups,
- no-wake count,
- actions executed,
- scheduled reviews,
- customer actions,
- approvals/rejections,
- duration.

Implement adaptive wake guidance:
- agent may emit bounded guidance,
- validate/persist it,
- classifier may consume it safely.

Implement Continue-As-New:
- use Temporal's supported Python approach,
- carry only compact essential state,
- configurable threshold,
- low dev/test threshold,
- verify run identity and product timeline remain coherent.

Add templates:
- Standard,
- VIP / High-Touch,
- Cost-Conscious.

Add tests around P2 behavior.

Exit gate:
P2 works without destabilizing P0/P1.

Then STOP.

---

## STAGE 7 — Final Hardening + Documentation + Submission Readiness

Goal: turn the project into a strong assignment submission.

Do:
- full regression pass,
- fix important TODOs,
- remove dead code,
- improve error states,
- verify fresh setup,
- finalize `.env.example`,
- finalize migrations/setup instructions,
- document Temporal local setup,
- document real LLM + mock mode,
- finalize architecture note,
- explain Workflow vs Activity responsibilities,
- explain Signals, Queries, timers, lifecycle authority,
- explain memory compaction,
- explain wake policy/classifier,
- explain approval gates,
- explain Continue-As-New,
- document known tradeoffs,
- add demo script,
- add walkthrough-video checklist,
- make README concise but complete.

Verify:
- frontend build,
- backend tests,
- Temporal tests,
- type/lint checks,
- Happy Path,
- Delivery Crisis path,
- terminate path,
- approval path,
- completion/final output.

Final architecture/demo story:

```text
Order created
   ↓
Temporal workflow owns lifecycle
   ↓
event arrives as Signal
   ↓
wake policy decides whether main AI is needed
   ↓
Agent Activity makes structured decision
   ↓
allowed business Action Activities execute
   ↓
timeline + memory update
   ↓
durable sleep
   ↓
Signal OR timer wakes workflow
   ↓
repeat
   ↓
deterministic terminal lifecycle rule
   ↓
final summary + learnings + recommendations
```

Then STOP and provide the final suggested Git commit message.

---

# 16. Recommended Demo Scenario

Make this class of scenario easy and reliable to demonstrate:

1. Start a VIP order.
2. Agent runs at workflow start and decides no action; sleeps.
3. Inject `payment_confirmed`.
4. Show wake policy deciding not to invoke main agent if no intervention is required.
5. Add live instruction: `If shipment is delayed, escalate immediately.`
6. Inject `shipment_delayed`.
7. Show signal -> immediate wake -> decision -> `message_logistics_team` -> `create_internal_note` -> next wake.
8. Inject customer message: `Where is my order? I need it tomorrow.`
9. Agent proposes `message_customer`.
10. Approval policy blocks execution.
11. Approve it from UI.
12. Demonstrate worker restart while workflow is durably sleeping.
13. Inject `delivered`.
14. Workflow-owned lifecycle completes.
15. Display final summary, important actions, learnings, recommendations, and analytics.

Optimize implementation decisions for this demo to be reliable.

---

# 17. Final Quality Bar

The submission should communicate:

> This is a durable, event-driven AI supervisor. Temporal owns the long-running lifecycle. Signals and timers wake it. AI reasoning occurs in Activities. The agent can take auditable business actions and maintain compact memory, while deterministic workflow rules retain lifecycle authority.

A smaller reliable implementation is preferable to a larger unfinished one.

Do not sacrifice:
- Temporal correctness,
- replay safety,
- clear state modeling,
- end-to-end reliability,
- understandable code,
- demo reliability

for decorative features.

---

# 18. Begin

Start with **STAGE 0 only**.

Do not implement Stage 1 or beyond in the same turn/session.

At the end of Stage 0:
- validate it,
- update `PROJECT_STATUS.md`,
- do not commit,
- do not push,
- provide the exact suggested commit message and manual Git commands,
- state that Stage 1 has not been started,
- wait for the user to reply `CONTINUE`.
