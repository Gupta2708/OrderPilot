"""OrderSupervisorWorkflow: Temporal owns the order lifecycle.

Stage 1 keeps every decision deterministic and in-workflow. There are no
Activities yet, so nothing here performs I/O and the workflow is fully
replay-safe. Stage 2 moves decision making into an Agent Activity without
changing the lifecycle rules that live here.
"""

from datetime import datetime, timedelta
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.domain.decision import DecisionKind, SupervisorDecision, Trigger, decide
    from app.domain.events import OrderEvent, parse_event
    from app.domain.lifecycle import (
        RunStatus,
        TerminalReason,
        status_for_terminal_reason,
        terminal_reason_for_event,
    )
    from app.domain.order_state import apply_event, initial_order_state
    from app.domain.wake_policy import WakeAggressiveness, WakeEvaluation, evaluate_wake
    from app.temporal.types import RunParams, RunResult

MAX_TIMELINE_ENTRIES = 500
MAX_MEMORY_LINES = 12


class ActivityType:
    """Unified timeline entry types; mirrors the `activities` table."""

    RUN_STARTED = "RUN_STARTED"
    EVENT_RECEIVED = "EVENT_RECEIVED"
    EVENT_REJECTED = "EVENT_REJECTED"
    EVENT_DUPLICATE_IGNORED = "EVENT_DUPLICATE_IGNORED"
    WAKE_DECISION = "WAKE_DECISION"
    AGENT_DECISION = "AGENT_DECISION"
    ACTION_PROPOSED = "ACTION_PROPOSED"
    MEMORY_UPDATED = "MEMORY_UPDATED"
    SLEEP_SCHEDULED = "SLEEP_SCHEDULED"
    INSTRUCTION_ADDED = "INSTRUCTION_ADDED"
    RUN_PAUSED = "RUN_PAUSED"
    RUN_RESUMED = "RUN_RESUMED"
    RUN_TERMINATED = "RUN_TERMINATED"
    RUN_COMPLETED = "RUN_COMPLETED"
    FINAL_OUTPUT = "FINAL_OUTPUT"


@workflow.defn(name="OrderSupervisorWorkflow")
class OrderSupervisorWorkflow:
    def __init__(self) -> None:
        self._params: RunParams | None = None
        self._started_at: datetime | None = None
        self._status: RunStatus = RunStatus.PENDING
        self._order_state: dict[str, Any] = initial_order_state()
        self._pending_events: list[OrderEvent] = []
        self._seen_event_ids: set[str] = set()
        self._instructions: list[str] = []
        self._timeline: list[dict[str, Any]] = []
        self._memory_lines: list[str] = []
        self._latest_decision: dict[str, Any] | None = None
        self._latest_wake: dict[str, Any] | None = None
        self._next_wake_at: datetime | None = None
        self._last_wake_at: datetime | None = None
        self._paused = False
        self._terminate_requested = False
        self._terminate_reason = ""
        self._terminal_reason: TerminalReason | None = None
        self._sequence = 0
        self._stats: dict[str, int] = {
            "events_received": 0,
            "agent_wakeups": 0,
            "no_wake_events": 0,
            "actions_proposed": 0,
            "scheduled_reviews": 0,
            "instructions_added": 0,
        }

    # ------------------------------------------------------------------ run

    @workflow.run
    async def run(self, params: RunParams) -> RunResult:
        self._params = params
        self._started_at = workflow.now()
        self._instructions.extend(params.initial_instructions)
        self._record(
            ActivityType.RUN_STARTED,
            {
                "order_id": params.order_id,
                "supervisor": params.supervisor_name,
                "allowed_actions": params.allowed_actions,
                "order_context": params.order_context,
            },
        )

        # Wake 1 of 3: workflow start.
        self._wake(Trigger.WORKFLOW_START, None, None)

        while self._terminal_reason is None:
            if self._terminate_requested:
                self._terminal_reason = TerminalReason.MANUAL_TERMINATE
                break

            if self._paused:
                # A paused run takes no agent action but stays terminable.
                await workflow.wait_condition(lambda: not self._paused or self._terminate_requested)
                continue

            timeout = self._seconds_until_next_wake()
            if timeout > 0:
                try:
                    # Durable wait: no polling. Wakes on Signal or on the timer.
                    await workflow.wait_condition(self._needs_attention, timeout=timeout)
                except TimeoutError:
                    if self._max_age_reached():
                        self._terminal_reason = TerminalReason.MAX_AGE_REACHED
                        break
                    # Wake 3 of 3: scheduled review.
                    self._stats["scheduled_reviews"] += 1
                    self._wake(Trigger.SCHEDULED_TIMER, None, None)
                    continue
            elif self._max_age_reached():
                self._terminal_reason = TerminalReason.MAX_AGE_REACHED
                break

            if self._terminate_requested:
                self._terminal_reason = TerminalReason.MANUAL_TERMINATE
                break
            if self._paused:
                continue

            self._drain_pending_events()

        return self._finalize()

    # -------------------------------------------------------------- signals

    @workflow.signal(name="order_event")
    def order_event(self, raw_event: dict[str, Any]) -> None:
        """Inbound lifecycle event, validated so bad input cannot corrupt state."""
        try:
            event = parse_event(raw_event)
        except ValueError as error:
            self._record(ActivityType.EVENT_REJECTED, {"error": str(error), "raw": raw_event})
            return
        if event.event_id in self._seen_event_ids:
            self._record(ActivityType.EVENT_DUPLICATE_IGNORED, {"event_id": event.event_id})
            return
        self._seen_event_ids.add(event.event_id)
        self._pending_events.append(event)

    @workflow.signal(name="add_instruction")
    def add_instruction(self, instruction: str) -> None:
        """Live run-specific guidance; affects every subsequent decision."""
        cleaned = instruction.strip()
        if not cleaned:
            return
        self._instructions.append(cleaned)
        self._stats["instructions_added"] += 1
        self._record(ActivityType.INSTRUCTION_ADDED, {"instruction": cleaned})

    @workflow.signal(name="pause")
    def pause(self) -> None:
        if self._paused:
            return
        self._paused = True
        self._record(ActivityType.RUN_PAUSED, {})

    @workflow.signal(name="resume")
    def resume(self) -> None:
        if not self._paused:
            return
        self._paused = False
        self._record(ActivityType.RUN_RESUMED, {})

    @workflow.signal(name="terminate")
    def terminate(self, reason: str = "Manually terminated") -> None:
        """Works while sleeping and while paused."""
        self._terminate_requested = True
        self._terminate_reason = reason
        self._record(ActivityType.RUN_TERMINATED, {"reason": reason})

    # -------------------------------------------------------------- queries

    @workflow.query(name="state")
    def state(self) -> dict[str, Any]:
        return {
            "run_id": self._params.run_id if self._params else "",
            "order_id": self._params.order_id if self._params else "",
            "status": str(self._current_status()),
            "paused": self._paused,
            "terminated": self._terminate_requested,
            "terminal": self._terminal_reason is not None,
            "terminal_reason": str(self._terminal_reason) if self._terminal_reason else None,
            "order_state": self._order_state,
            "memory_summary": self._memory_summary(),
            "run_instructions": list(self._instructions),
            "latest_decision": self._latest_decision,
            "latest_wake_decision": self._latest_wake,
            "next_wake_at": self._iso(self._next_wake_at),
            "last_wake_at": self._iso(self._last_wake_at),
            "pending_events": len(self._pending_events),
            "stats": dict(self._stats),
        }

    @workflow.query(name="timeline")
    def timeline(self, limit: int = 50) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        return self._timeline[-limit:]

    # ------------------------------------------------------------- internals

    def _needs_attention(self) -> bool:
        return bool(self._pending_events) or self._terminate_requested or self._paused

    def _max_age_reached(self) -> bool:
        assert self._params is not None and self._started_at is not None
        age_limit = self._started_at + timedelta(minutes=self._params.max_age_minutes)
        return workflow.now() >= age_limit

    def _seconds_until_next_wake(self) -> float:
        """Seconds until the earlier of the next review and the max-age deadline."""
        assert self._params is not None and self._started_at is not None
        now = workflow.now()
        age_limit = self._started_at + timedelta(minutes=self._params.max_age_minutes)
        target = min(self._next_wake_at or age_limit, age_limit)
        return max((target - now).total_seconds(), 0.0)

    def _drain_pending_events(self) -> None:
        while self._pending_events and not self._terminate_requested and not self._paused:
            event = self._pending_events.pop(0)
            self._stats["events_received"] += 1
            self._record(
                ActivityType.EVENT_RECEIVED,
                {"event_id": event.event_id, "type": event.type, "payload": event.payload},
            )
            self._order_state = apply_event(self._order_state, event)

            evaluation = evaluate_wake(event, self._aggressiveness())
            self._latest_wake = dict(evaluation.as_dict())
            self._latest_wake["event_id"] = event.event_id
            self._latest_wake["event_type"] = event.type
            self._record(ActivityType.WAKE_DECISION, self._latest_wake)

            if evaluation.wake_now:
                # Wake 2 of 3: important Signal.
                self._wake(Trigger.SIGNAL, event, evaluation)
            else:
                self._stats["no_wake_events"] += 1

            # Lifecycle authority stays with the workflow, never with a decision.
            reason = terminal_reason_for_event(event)
            if reason is not None:
                self._terminal_reason = reason
                return

    def _wake(
        self,
        trigger: Trigger,
        event: OrderEvent | None,
        evaluation: WakeEvaluation | None,
    ) -> None:
        assert self._params is not None
        self._status = RunStatus.ACTING
        self._last_wake_at = workflow.now()
        self._stats["agent_wakeups"] += 1

        decision = decide(
            trigger=trigger,
            event=event,
            wake_evaluation=evaluation,
            order_state=self._order_state,
            instructions=tuple(self._instructions),
            allowed_actions=frozenset(self._params.allowed_actions),
            default_wake_minutes=self._params.default_wake_minutes,
        )
        self._latest_decision = dict(decision.as_dict())
        self._latest_decision["trigger"] = str(trigger)
        self._record(ActivityType.AGENT_DECISION, self._latest_decision)
        self._apply_decision(decision)

    def _apply_decision(self, decision: SupervisorDecision) -> None:
        # Stage 1 records intent only; Stage 2 executes these via Activities.
        for action in decision.actions:
            self._stats["actions_proposed"] += 1
            self._record(ActivityType.ACTION_PROPOSED, action.as_dict())

        if decision.memory_update:
            self._memory_lines.append(decision.memory_update)
            if len(self._memory_lines) > MAX_MEMORY_LINES:
                # Simple deterministic compaction; Stage 2 adds a real Activity.
                self._memory_lines = self._memory_lines[-MAX_MEMORY_LINES:]
            self._record(ActivityType.MEMORY_UPDATED, {"memory_update": decision.memory_update})

        if decision.decision is DecisionKind.NO_ACTION:
            self._status = RunStatus.SLEEPING
        self._schedule_sleep(decision.sleep_minutes)

    def _schedule_sleep(self, minutes: int) -> None:
        safe_minutes = max(1, minutes)
        self._next_wake_at = workflow.now() + timedelta(minutes=safe_minutes)
        self._status = RunStatus.SLEEPING
        self._record(
            ActivityType.SLEEP_SCHEDULED,
            {"minutes": safe_minutes, "next_wake_at": self._iso(self._next_wake_at)},
        )

    def _finalize(self) -> RunResult:
        assert self._params is not None and self._started_at is not None
        reason = self._terminal_reason or TerminalReason.MANUAL_TERMINATE
        self._status = status_for_terminal_reason(reason)
        self._next_wake_at = None  # A terminal run never schedules another wake.

        important = [
            entry["payload"]
            for entry in self._timeline
            if entry["type"] == ActivityType.ACTION_PROPOSED
        ]
        duration_seconds = int((workflow.now() - self._started_at).total_seconds())
        stats = dict(self._stats)
        stats["duration_seconds"] = duration_seconds

        summary = (
            f"Order {self._params.order_id} finished as {self._status} ({reason}). "
            f"Handled {self._stats['events_received']} events with "
            f"{self._stats['agent_wakeups']} agent wake-ups and "
            f"{self._stats['actions_proposed']} proposed actions."
        )

        self._record(
            ActivityType.RUN_COMPLETED
            if self._status is RunStatus.COMPLETED
            else ActivityType.RUN_TERMINATED,
            {"terminal_reason": str(reason)},
        )
        result = RunResult(
            run_id=self._params.run_id,
            order_id=self._params.order_id,
            status=str(self._status),
            terminal_reason=str(reason),
            final_summary=summary,
            important_actions=important,
            learnings=self._learnings(),
            recommendations=self._recommendations(),
            stats=stats,
            order_state=self._order_state,
            memory_summary=self._memory_summary(),
        )
        self._record(ActivityType.FINAL_OUTPUT, {"final_summary": summary, "stats": stats})
        return result

    def _learnings(self) -> list[str]:
        learnings: list[str] = []
        if self._order_state.get("payment", {}).get("status") == "failed":
            learnings.append("Payment failed at least once and needed payments-team attention.")
        if self._order_state.get("shipment", {}).get("status") == "delayed":
            learnings.append("Shipment was delayed; delivery risk appeared mid-run.")
        if self._stats["no_wake_events"]:
            count = self._stats["no_wake_events"]
            learnings.append(
                f"{count} routine event{'s' if count != 1 else ''} "
                f"{'were' if count != 1 else 'was'} absorbed without waking the main agent."
            )
        return learnings or ["Order progressed without notable incidents."]

    def _recommendations(self) -> list[str]:
        if self._terminal_reason is TerminalReason.MAX_AGE_REACHED:
            return ["Run hit its maximum age; review whether the age limit fits this order type."]
        if self._terminal_reason is TerminalReason.MANUAL_TERMINATE:
            return [f"Run was terminated manually: {self._terminate_reason}."]
        return ["No process changes recommended for this run."]

    def _memory_summary(self) -> str:
        return "\n".join(self._memory_lines)

    def _aggressiveness(self) -> WakeAggressiveness:
        assert self._params is not None
        try:
            return WakeAggressiveness(self._params.wake_aggressiveness)
        except ValueError:
            return WakeAggressiveness.BALANCED

    def _current_status(self) -> RunStatus:
        if self._terminal_reason is not None:
            return status_for_terminal_reason(self._terminal_reason)
        if self._paused:
            return RunStatus.PAUSED
        return self._status

    def _record(self, activity_type: str, payload: dict[str, Any]) -> None:
        self._sequence += 1
        self._timeline.append(
            {
                "seq": self._sequence,
                "type": activity_type,
                "at": self._iso(workflow.now()),
                "payload": payload,
            }
        )
        if len(self._timeline) > MAX_TIMELINE_ENTRIES:
            self._timeline = self._timeline[-MAX_TIMELINE_ENTRIES:]

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None
