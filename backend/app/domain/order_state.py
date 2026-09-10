from copy import deepcopy
from typing import Any

from app.domain.events import EventType, OrderEvent


def initial_order_state() -> dict[str, Any]:
    """Explicit structured order state, kept separate from natural-language memory."""
    return {
        "payment": {"status": "pending"},
        "fulfillment": {"status": "not_started"},
        "shipment": {"status": "not_created"},
        "delivery": {"status": "pending"},
        "refund": {"status": "none"},
        "customer": {"last_message": None},
    }


def apply_event(state: dict[str, Any], event: OrderEvent) -> dict[str, Any]:
    """Return a new order state with the event applied.

    Unknown event types leave the structured state untouched; they are handled by
    the wake policy instead of silently mutating the order.
    """
    updated = deepcopy(state)
    match event.type:
        case EventType.ORDER_CREATED:
            updated["fulfillment"]["status"] = "awaiting_payment"
        case EventType.PAYMENT_CONFIRMED:
            updated["payment"]["status"] = "confirmed"
            updated["fulfillment"]["status"] = "ready_to_pick"
        case EventType.PAYMENT_FAILED:
            updated["payment"]["status"] = "failed"
            updated["payment"]["reason"] = event.payload.get("reason")
        case EventType.SHIPMENT_CREATED:
            updated["shipment"]["status"] = "created"
            updated["shipment"]["tracking_id"] = event.payload.get("tracking_id")
            updated["fulfillment"]["status"] = "shipped"
        case EventType.SHIPMENT_DELAYED:
            updated["shipment"]["status"] = "delayed"
            updated["shipment"]["delay_reason"] = event.payload.get("reason")
        case EventType.DELIVERED:
            updated["delivery"]["status"] = "delivered"
            updated["shipment"]["status"] = "delivered"
        case EventType.REFUND_REQUESTED:
            updated["refund"]["status"] = "requested"
            updated["refund"]["reason"] = event.payload.get("reason")
        case EventType.REFUND_COMPLETED:
            updated["refund"]["status"] = "completed"
        case EventType.ORDER_CANCELLED:
            updated["fulfillment"]["status"] = "cancelled"
        case EventType.CUSTOMER_MESSAGE_RECEIVED:
            updated["customer"]["last_message"] = event.payload.get("message")
    return updated
