"""Stage 1 placeholder decision maker.

Deliberately deterministic so Temporal lifecycle behaviour can be proven before
any LLM is involved. Stage 2 replaces this with a real agent Activity returning
the same shape, validated with Pydantic.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.domain.actions import BusinessAction
from app.domain.events import EventType, OrderEvent
from app.domain.wake_policy import Severity, WakeEvaluation


class Trigger(StrEnum):
    WORKFLOW_START = "WORKFLOW_START"
    SIGNAL = "SIGNAL"
    SCHEDULED_TIMER = "SCHEDULED_TIMER"


class DecisionKind(StrEnum):
    ACT = "ACT"
    SLEEP = "SLEEP"
    NO_ACTION = "NO_ACTION"


@dataclass(frozen=True)
class ProposedAction:
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"tool": self.tool, "arguments": self.arguments}


@dataclass(frozen=True)
class SupervisorDecision:
    """Structured decision. Mirrors the agent contract used from Stage 2 onward."""

    decision: DecisionKind
    priority: Severity
    reason_summary: str
    actions: tuple[ProposedAction, ...]
    memory_update: str
    sleep_minutes: int
    completion_recommended: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": str(self.decision),
            "priority": str(self.priority),
            "reason_summary": self.reason_summary,
            "actions": [action.as_dict() for action in self.actions],
            "memory_update": self.memory_update,
            "sleep_minutes": self.sleep_minutes,
            "completion_recommended": self.completion_recommended,
            "source": "deterministic_placeholder",
        }


# Which action each notable event would call for, before allow-list filtering.
_ACTION_BY_EVENT: dict[str, BusinessAction] = {
    EventType.PAYMENT_FAILED: BusinessAction.MESSAGE_PAYMENTS_TEAM,
    EventType.SHIPMENT_DELAYED: BusinessAction.MESSAGE_LOGISTICS_TEAM,
    EventType.REFUND_REQUESTED: BusinessAction.MESSAGE_FULFILLMENT_TEAM,
    EventType.CUSTOMER_MESSAGE_RECEIVED: BusinessAction.MESSAGE_CUSTOMER,
}

_URGENT_SLEEP_MINUTES = 15


def _allowed(
    actions: tuple[ProposedAction, ...], allowed_actions: frozenset[str]
) -> tuple[ProposedAction, ...]:
    """Never propose a tool the supervisor configuration does not permit."""
    return tuple(action for action in actions if action.tool in allowed_actions)


def decide(
    trigger: Trigger,
    event: OrderEvent | None,
    wake_evaluation: WakeEvaluation | None,
    order_state: dict[str, Any],
    instructions: tuple[str, ...],
    allowed_actions: frozenset[str],
    default_wake_minutes: int,
) -> SupervisorDecision:
    """Produce a structured decision from current state. Pure and replay-safe."""
    if trigger is Trigger.WORKFLOW_START:
        return SupervisorDecision(
            decision=DecisionKind.SLEEP,
            priority=Severity.LOW,
            reason_summary="Run started; order is healthy so far. Scheduling first review.",
            actions=(),
            memory_update="Supervision started; awaiting order lifecycle events.",
            sleep_minutes=default_wake_minutes,
            completion_recommended=False,
        )

    if trigger is Trigger.SCHEDULED_TIMER:
        stalled = order_state.get("shipment", {}).get("status") == "delayed"
        note = _allowed(
            (
                ProposedAction(
                    tool=BusinessAction.CREATE_INTERNAL_NOTE,
                    arguments={"note": "Scheduled review: shipment still delayed."},
                ),
            ),
            allowed_actions,
        )
        if stalled and note:
            return SupervisorDecision(
                decision=DecisionKind.ACT,
                priority=Severity.MEDIUM,
                reason_summary="Scheduled review found the shipment still delayed.",
                actions=note,
                memory_update="Scheduled review: shipment still delayed; logged internal note.",
                sleep_minutes=default_wake_minutes,
                completion_recommended=False,
            )
        return SupervisorDecision(
            decision=DecisionKind.NO_ACTION,
            priority=Severity.LOW,
            reason_summary="Scheduled review found no issue requiring intervention.",
            actions=(),
            memory_update="Scheduled review: no intervention required.",
            sleep_minutes=default_wake_minutes,
            completion_recommended=False,
        )

    # Signal-driven wake.
    assert event is not None and wake_evaluation is not None
    proposed: tuple[ProposedAction, ...] = ()
    mapped = _ACTION_BY_EVENT.get(event.type)
    if mapped is not None:
        proposed = (
            ProposedAction(
                tool=mapped,
                arguments={"order_event": event.type, "reason": wake_evaluation.reason},
            ),
        )
    if instructions:
        proposed += (
            ProposedAction(
                tool=BusinessAction.CREATE_INTERNAL_NOTE,
                arguments={"note": f"Applying run instruction: {instructions[-1]}"},
            ),
        )
    proposed = _allowed(proposed, allowed_actions)

    urgent = wake_evaluation.severity in (Severity.HIGH, Severity.CRITICAL)
    return SupervisorDecision(
        decision=DecisionKind.ACT if proposed else DecisionKind.NO_ACTION,
        priority=wake_evaluation.severity,
        reason_summary=f"Woken by '{event.type}': {wake_evaluation.reason}",
        actions=proposed,
        memory_update=f"Handled '{event.type}' ({wake_evaluation.severity}).",
        sleep_minutes=_URGENT_SLEEP_MINUTES if urgent else default_wake_minutes,
        completion_recommended=event.type == EventType.DELIVERED,
    )
