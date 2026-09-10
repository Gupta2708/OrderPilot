from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    """Order lifecycle events the supervisor understands natively."""

    ORDER_CREATED = "order_created"
    PAYMENT_CONFIRMED = "payment_confirmed"
    PAYMENT_FAILED = "payment_failed"
    SHIPMENT_CREATED = "shipment_created"
    SHIPMENT_DELAYED = "shipment_delayed"
    DELIVERED = "delivered"
    REFUND_REQUESTED = "refund_requested"
    REFUND_COMPLETED = "refund_completed"
    ORDER_CANCELLED = "order_cancelled"
    CUSTOMER_MESSAGE_RECEIVED = "customer_message_received"


KNOWN_EVENT_TYPES = frozenset(str(member) for member in EventType)


@dataclass
class OrderEvent:
    """A single inbound lifecycle event.

    `type` stays a plain string so unknown event types survive intact and can be
    escalated rather than rejected.
    """

    event_id: str
    type: str
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def is_known(self) -> bool:
        return self.type in KNOWN_EVENT_TYPES


def parse_event(raw: dict[str, Any]) -> OrderEvent:
    """Validate an untrusted event payload.

    Raises ValueError so a malformed Signal cannot corrupt workflow state.
    """
    event_id = raw.get("event_id")
    event_type = raw.get("type")
    if not isinstance(event_id, str) or not event_id.strip():
        raise ValueError("event_id must be a non-empty string")
    if not isinstance(event_type, str) or not event_type.strip():
        raise ValueError("type must be a non-empty string")
    payload = raw.get("payload", {})
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    return OrderEvent(event_id=event_id.strip(), type=event_type.strip(), payload=dict(payload))
