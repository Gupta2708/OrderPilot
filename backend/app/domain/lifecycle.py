from enum import StrEnum

from app.domain.events import EventType, OrderEvent


class RunStatus(StrEnum):
    """Product-facing run status. The workflow, never the model, owns transitions."""

    PENDING = "PENDING"
    ACTING = "ACTING"
    SLEEPING = "SLEEPING"
    PAUSED = "PAUSED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    TERMINATED = "TERMINATED"


class TerminalReason(StrEnum):
    DELIVERED = "delivered"
    REFUND_COMPLETED = "refund_completed"
    ORDER_CANCELLED = "order_cancelled"
    MANUAL_TERMINATE = "manual_terminate"
    MAX_AGE_REACHED = "max_age_reached"


TERMINAL_STATUSES = frozenset({RunStatus.COMPLETED, RunStatus.TERMINATED})

_TERMINAL_EVENTS: dict[str, TerminalReason] = {
    EventType.DELIVERED: TerminalReason.DELIVERED,
    EventType.REFUND_COMPLETED: TerminalReason.REFUND_COMPLETED,
    EventType.ORDER_CANCELLED: TerminalReason.ORDER_CANCELLED,
}


def terminal_reason_for_event(event: OrderEvent) -> TerminalReason | None:
    """Deterministic terminal rule: only these events end a run on their own."""
    return _TERMINAL_EVENTS.get(event.type)


def status_for_terminal_reason(reason: TerminalReason) -> RunStatus:
    if reason is TerminalReason.MANUAL_TERMINATE:
        return RunStatus.TERMINATED
    return RunStatus.COMPLETED
