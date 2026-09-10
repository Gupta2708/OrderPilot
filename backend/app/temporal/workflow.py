"""OrderSupervisorWorkflow: Temporal owns the order lifecycle.

The workflow itself performs no I/O. Agent inference, business actions, memory
compaction, and final-summary generation all run as Activities, so this code
stays deterministic and replay-safe. Lifecycle authority lives here and nowhere
else: the agent may recommend completion, but only the rules in this file end a
run.
"""

from datetime import datetime, timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.domain.events import OrderEvent, parse_event
    from app.domain.lifecycle import (
        RunStatus,
        TerminalReason,
        status_for_terminal_reason,
        terminal_reason_for_event,
    )
    from app.domain.order_state import apply_event, initial_order_state
    from app.domain.wake_policy import WakeAggressiveness, WakeEvaluation, evaluate_wake
    from app.temporal.activities import (
        ActionRequest,
        DecisionRequest,
        DecisionResponse,
        FinalizeRequest,
        FinalizeResponse,
        MemoryRequest,
        compact_run_memory,
        finalize_run,
        make_decision,
        run_business_action,
    )
    from app.temporal.types import RunParams, RunResult

MAX_TIMELINE_ENTRIES = 500
RECENT_ACTIVITY_WINDOW = 8

DECISION_RETRY = RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=1))
ACTION_RETRY = RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=1))

DECISION_TIMEOUT = timedelta(minutes=2)
ACTION_TIMEOUT = timedelta(seconds=30)
MEMORY_TIMEOUT = timedelta(seconds=30)
FINALIZE_TIMEOUT = timedelta(minutes=1)


class ActivityType:
    """Unified timeline entry types; mirrors the `activities` table."""

    RUN_STARTED = "RUN_STARTED"
    EVENT_RECEIVED = "EVENT_RECEIVED"
    EVENT_REJECTED = "EVENT_REJECTED"
    EVENT_DUPLICATE_IGNORED = "EVENT_DUPLICATE_IGNORED"
    WAKE_DECISION = "WAKE_DECISION"
    AGENT_DECISION = "AGENT_DECISION"
    ACTION_EXECUTED = "ACTION_EXECUTED"
    ACTION_FAILED = "ACTION_FAILED"
    ACTION_REJECTED = "ACTION_REJECTED"
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
        self._memory_summary: str = ""
        self._executed_actions: list[dict[str, Any]] = []
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
            "actions_executed": 0,
            "actions_failed": 0,
            "actions_rejected": 0,
            "scheduled_reviews": 0,
            "instructions_added": 0,
            "fallback_decisions": 0,
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
        await self._wake("WORKFLOW_START", None, None)

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
                    await self._wake("SCHEDULED_TIMER", None, None)
                    continue
            elif self._max_age_reached():
                self._terminal_reason = TerminalReason.MAX_AGE_REACHED
                break

            if self._terminate_requested:
                self._terminal_reason = TerminalReason.MANUAL_TERMINATE
                break
            if self._paused:
                continue

            await self._drain_pending_events()

        return await self._finalize()

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
            "memory_summary": self._memory_summary,
            "run_instructions": list(self._instructions),
            "latest_decision": self._latest_decision,
            "latest_wake_decision": self._latest_wake,
            "executed_actions": list(self._executed_actions),
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

    async def _drain_pending_events(self) -> None:
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
                await self._wake("SIGNAL", event, evaluation)
            else:
                self._stats["no_wake_events"] += 1

            # Lifecycle authority stays with the workflow, never with a decision.
            reason = terminal_reason_for_event(event)
            if reason is not None:
                self._terminal_reason = reason
                return

    async def _wake(
        self,
        trigger: str,
        event: OrderEvent | None,
        evaluation: WakeEvaluation | None,
    ) -> None:
        assert self._params is not None
        self._status = RunStatus.ACTING
        self._last_wake_at = workflow.now()
        self._stats["agent_wakeups"] += 1

        request = DecisionRequest(
            order_id=self._params.order_id,
            trigger=trigger,
            base_instruction=self._params.base_instruction,
            run_instructions=list(self._instructions),
            order_state=self._order_state,
            memory_summary=self._memory_summary,
            triggering_event=(
                {"event_id": event.event_id, "type": event.type, "payload": event.payload}
                if event is not None
                else None
            ),
            wake_evaluation=evaluation.as_dict() if evaluation is not None else None,
            recent_activity=self._recent_activity(),
            allowed_actions=list(self._params.allowed_actions),
            default_wake_minutes=self._params.default_wake_minutes,
        )
        decision: DecisionResponse = await workflow.execute_activity(
            make_decision,
            request,
            start_to_close_timeout=DECISION_TIMEOUT,
            retry_policy=DECISION_RETRY,
        )

        if decision.fallback_used:
            self._stats["fallback_decisions"] += 1
        self._latest_decision = {
            "decision": decision.decision,
            "priority": decision.priority,
            "reason_summary": decision.reason_summary,
            "actions": decision.actions,
            "memory_update": decision.memory_update,
            "sleep_minutes": decision.sleep_minutes,
            "completion_recommended": decision.completion_recommended,
            "provider": decision.provider,
            "trigger": trigger,
        }
        self._record(ActivityType.AGENT_DECISION, self._latest_decision)

        for tool in decision.rejected_actions:
            self._stats["actions_rejected"] += 1
            self._record(ActivityType.ACTION_REJECTED, {"tool": tool, "reason": "not_allowed"})

        await self._execute_actions(decision.actions)
        await self._update_memory(decision.memory_update)
        self._schedule_sleep(decision.sleep_minutes)

    async def _execute_actions(self, actions: list[dict[str, Any]]) -> None:
        assert self._params is not None
        for action in actions:
            result: dict[str, Any] = await workflow.execute_activity(
                run_business_action,
                ActionRequest(
                    order_id=self._params.order_id,
                    tool=str(action.get("tool", "")),
                    arguments=dict(action.get("arguments", {})),
                    allowed_actions=list(self._params.allowed_actions),
                ),
                start_to_close_timeout=ACTION_TIMEOUT,
                retry_policy=ACTION_RETRY,
            )
            if result.get("ok"):
                self._stats["actions_executed"] += 1
                self._executed_actions.append(result)
                self._record(ActivityType.ACTION_EXECUTED, result)
            else:
                self._stats["actions_failed"] += 1
                self._record(ActivityType.ACTION_FAILED, result)

    async def _update_memory(self, memory_update: str) -> None:
        if not memory_update:
            return
        self._memory_summary = await workflow.execute_activity(
            compact_run_memory,
            MemoryRequest(existing=self._memory_summary, updates=[memory_update]),
            start_to_close_timeout=MEMORY_TIMEOUT,
            retry_policy=ACTION_RETRY,
        )
        self._record(ActivityType.MEMORY_UPDATED, {"memory_update": memory_update})

    def _schedule_sleep(self, minutes: int) -> None:
        safe_minutes = max(1, minutes)
        self._next_wake_at = workflow.now() + timedelta(minutes=safe_minutes)
        self._status = RunStatus.SLEEPING
        self._record(
            ActivityType.SLEEP_SCHEDULED,
            {"minutes": safe_minutes, "next_wake_at": self._iso(self._next_wake_at)},
        )

    async def _finalize(self) -> RunResult:
        assert self._params is not None and self._started_at is not None
        reason = self._terminal_reason or TerminalReason.MANUAL_TERMINATE
        self._status = status_for_terminal_reason(reason)
        self._next_wake_at = None  # A terminal run never schedules another wake.

        duration_seconds = int((workflow.now() - self._started_at).total_seconds())
        stats = dict(self._stats)
        stats["duration_seconds"] = duration_seconds

        final: FinalizeResponse = await workflow.execute_activity(
            finalize_run,
            FinalizeRequest(
                order_id=self._params.order_id,
                status=str(self._status),
                terminal_reason=str(reason),
                order_state=self._order_state,
                memory_summary=self._memory_summary,
                executed_actions=list(self._executed_actions),
                stats=stats,
            ),
            start_to_close_timeout=FINALIZE_TIMEOUT,
            retry_policy=ACTION_RETRY,
        )

        recommendations = list(final.recommendations)
        if reason is TerminalReason.MANUAL_TERMINATE:
            recommendations.insert(0, f"Run was terminated manually: {self._terminate_reason}.")

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
            final_summary=final.final_summary,
            important_actions=list(final.important_actions),
            learnings=list(final.learnings),
            recommendations=recommendations,
            stats=stats,
            order_state=self._order_state,
            memory_summary=self._memory_summary,
        )
        self._record(
            ActivityType.FINAL_OUTPUT, {"final_summary": final.final_summary, "stats": stats}
        )
        return result

    def _recent_activity(self) -> list[dict[str, Any]]:
        """A small, readable window of history for the prompt."""
        summaries: list[dict[str, Any]] = []
        for entry in self._timeline[-RECENT_ACTIVITY_WINDOW:]:
            payload = entry.get("payload", {})
            summary = (
                payload.get("type")
                or payload.get("reason_summary")
                or payload.get("detail")
                or payload.get("instruction")
                or ""
            )
            summaries.append({"type": entry["type"], "summary": str(summary)[:200]})
        return summaries

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
