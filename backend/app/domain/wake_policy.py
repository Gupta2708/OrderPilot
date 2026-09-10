from dataclasses import dataclass
from enum import StrEnum

from app.domain.events import EventType, OrderEvent


class Severity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class WakeAggressiveness(StrEnum):
    LOW = "LOW"
    BALANCED = "BALANCED"
    HIGH = "HIGH"


@dataclass(frozen=True)
class WakeEvaluation:
    """Auditable record of why the main agent was, or was not, woken."""

    wake_now: bool
    severity: Severity
    category: str
    reason: str
    rule: str

    def as_dict(self) -> dict[str, object]:
        return {
            "wake_now": self.wake_now,
            "severity": str(self.severity),
            "category": self.category,
            "reason": self.reason,
            "rule": self.rule,
        }


# Level A fast path. Deliberately small: it is a cheap filter, not the business brain.
_SEVERITY_BY_EVENT: dict[str, tuple[Severity, str]] = {
    EventType.PAYMENT_FAILED: (Severity.CRITICAL, "payment_risk"),
    EventType.REFUND_REQUESTED: (Severity.CRITICAL, "customer_risk"),
    EventType.ORDER_CANCELLED: (Severity.CRITICAL, "lifecycle"),
    EventType.SHIPMENT_DELAYED: (Severity.HIGH, "delivery_risk"),
    EventType.DELIVERED: (Severity.HIGH, "lifecycle"),
    EventType.REFUND_COMPLETED: (Severity.HIGH, "lifecycle"),
    EventType.ORDER_CREATED: (Severity.LOW, "lifecycle"),
    EventType.PAYMENT_CONFIRMED: (Severity.LOW, "payment"),
    EventType.SHIPMENT_CREATED: (Severity.LOW, "delivery"),
}

_ESCALATION_KEYWORDS = ("cancel", "refund", "urgent", "lawyer", "complaint", "tomorrow", "angry")

_WAKE_THRESHOLD: dict[WakeAggressiveness, Severity] = {
    WakeAggressiveness.LOW: Severity.CRITICAL,
    WakeAggressiveness.BALANCED: Severity.HIGH,
    WakeAggressiveness.HIGH: Severity.LOW,
}

_SEVERITY_ORDER = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]


def _at_least(severity: Severity, threshold: Severity) -> bool:
    return _SEVERITY_ORDER.index(severity) >= _SEVERITY_ORDER.index(threshold)


def _classify_customer_message(event: OrderEvent) -> tuple[Severity, str, str]:
    message = str(event.payload.get("message") or "").lower()
    if event.payload.get("urgent") is True or any(k in message for k in _ESCALATION_KEYWORDS):
        return Severity.HIGH, "customer_risk", "Customer message signals escalation risk."
    return Severity.LOW, "customer", "Routine customer message; state updated without waking."


def needs_classification(event: OrderEvent) -> bool:
    """True when the cheap rules cannot honestly answer on their own.

    Unknown event types have no entry in the table, and a customer message can
    mean anything from "thanks!" to "I am cancelling and calling my lawyer".
    These are the cases Level B exists for.
    """
    return (not event.is_known) or event.type == EventType.CUSTOMER_MESSAGE_RECEIVED


def meets_threshold(severity: Severity, aggressiveness: WakeAggressiveness) -> bool:
    """Whether a severity is high enough to wake at this sensitivity."""
    return _at_least(severity, _WAKE_THRESHOLD[aggressiveness])


def evaluate_fast_path(
    event: OrderEvent,
    aggressiveness: WakeAggressiveness = WakeAggressiveness.BALANCED,
) -> WakeEvaluation | None:
    """Level A only. Returns None when the decision should be classified."""
    if needs_classification(event):
        return None
    severity, category = _SEVERITY_BY_EVENT[event.type]
    wake_now = meets_threshold(severity, aggressiveness)
    reason = (
        f"'{event.type}' is {severity} severity, at or above the {aggressiveness} wake threshold."
        if wake_now
        else f"'{event.type}' is {severity} severity; state updated without waking the agent."
    )
    return WakeEvaluation(
        wake_now=wake_now,
        severity=severity,
        category=category,
        reason=reason,
        rule="deterministic_severity_table",
    )


def evaluate_wake(
    event: OrderEvent,
    aggressiveness: WakeAggressiveness = WakeAggressiveness.BALANCED,
) -> WakeEvaluation:
    """Fully deterministic evaluation of any event.

    Used as the safe fallback when the classifier is unavailable or returns
    something unusable, and by the mock provider.
    """
    threshold = _WAKE_THRESHOLD[aggressiveness]

    if not event.is_known:
        return WakeEvaluation(
            wake_now=True,
            severity=Severity.MEDIUM,
            category="unknown",
            reason=f"Unrecognised event type '{event.type}'; escalating for review.",
            rule="unknown_event_escalation",
        )

    if event.type == EventType.CUSTOMER_MESSAGE_RECEIVED:
        severity, category, reason = _classify_customer_message(event)
        return WakeEvaluation(
            wake_now=_at_least(severity, threshold),
            severity=severity,
            category=category,
            reason=reason,
            rule="customer_message_keywords",
        )

    severity, category = _SEVERITY_BY_EVENT[event.type]
    wake_now = _at_least(severity, threshold)
    reason = (
        f"'{event.type}' is {severity} severity, at or above the {aggressiveness} wake threshold."
        if wake_now
        else f"'{event.type}' is {severity} severity; state updated without waking the agent."
    )
    return WakeEvaluation(
        wake_now=wake_now,
        severity=severity,
        category=category,
        reason=reason,
        rule="deterministic_severity_table",
    )
