import pytest

from app.domain.actions import ALL_ACTIONS, BusinessAction
from app.domain.decision import DecisionKind, Trigger, decide
from app.domain.events import EventType, OrderEvent, parse_event
from app.domain.lifecycle import (
    RunStatus,
    TerminalReason,
    status_for_terminal_reason,
    terminal_reason_for_event,
)
from app.domain.order_state import apply_event, initial_order_state
from app.domain.wake_policy import Severity, WakeAggressiveness, evaluate_wake

ALLOWED = frozenset(ALL_ACTIONS)


def _event(event_type: str, **payload: object) -> OrderEvent:
    return OrderEvent(event_id=f"e-{event_type}", type=event_type, payload=dict(payload))


def test_parse_event_rejects_malformed_payloads() -> None:
    with pytest.raises(ValueError):
        parse_event({"type": "delivered"})
    with pytest.raises(ValueError):
        parse_event({"event_id": " ", "type": "delivered"})
    with pytest.raises(ValueError):
        parse_event({"event_id": "e1", "type": "delivered", "payload": "not-an-object"})

    parsed = parse_event({"event_id": " e1 ", "type": " delivered "})
    assert parsed.event_id == "e1"
    assert parsed.type == "delivered"
    assert parsed.is_known


def test_apply_event_updates_structured_state_without_mutating_input() -> None:
    state = initial_order_state()
    updated = apply_event(state, _event(EventType.PAYMENT_CONFIRMED))
    assert state["payment"]["status"] == "pending"
    assert updated["payment"]["status"] == "confirmed"

    delayed = apply_event(updated, _event(EventType.SHIPMENT_DELAYED, reason="weather"))
    assert delayed["shipment"]["status"] == "delayed"
    assert delayed["shipment"]["delay_reason"] == "weather"


def test_unknown_event_leaves_state_untouched() -> None:
    state = initial_order_state()
    assert apply_event(state, _event("warehouse_fire")) == state


def test_routine_events_do_not_wake_the_agent() -> None:
    for event_type in (EventType.PAYMENT_CONFIRMED, EventType.SHIPMENT_CREATED):
        evaluation = evaluate_wake(_event(event_type))
        assert evaluation.wake_now is False
        assert evaluation.severity is Severity.LOW


def test_critical_events_wake_the_agent() -> None:
    for event_type in (EventType.PAYMENT_FAILED, EventType.SHIPMENT_DELAYED):
        assert evaluate_wake(_event(event_type)).wake_now is True


def test_unknown_events_are_escalated_not_dropped() -> None:
    evaluation = evaluate_wake(_event("warehouse_fire"))
    assert evaluation.wake_now is True
    assert evaluation.category == "unknown"
    assert evaluation.rule == "unknown_event_escalation"


def test_customer_message_wakes_only_when_it_signals_risk() -> None:
    routine = evaluate_wake(_event(EventType.CUSTOMER_MESSAGE_RECEIVED, message="Thanks!"))
    assert routine.wake_now is False

    risky = evaluate_wake(
        _event(EventType.CUSTOMER_MESSAGE_RECEIVED, message="I need it tomorrow or I cancel")
    )
    assert risky.wake_now is True
    assert risky.category == "customer_risk"


def test_wake_aggressiveness_shifts_the_threshold() -> None:
    routine = _event(EventType.PAYMENT_CONFIRMED)
    assert evaluate_wake(routine, WakeAggressiveness.HIGH).wake_now is True
    assert evaluate_wake(routine, WakeAggressiveness.LOW).wake_now is False

    delayed = _event(EventType.SHIPMENT_DELAYED)
    assert evaluate_wake(delayed, WakeAggressiveness.LOW).wake_now is False
    assert evaluate_wake(delayed, WakeAggressiveness.BALANCED).wake_now is True


def test_decision_never_proposes_a_disallowed_action() -> None:
    event = _event(EventType.SHIPMENT_DELAYED)
    decision = decide(
        trigger=Trigger.SIGNAL,
        event=event,
        wake_evaluation=evaluate_wake(event),
        order_state=initial_order_state(),
        instructions=(),
        allowed_actions=frozenset({BusinessAction.CREATE_INTERNAL_NOTE}),
        default_wake_minutes=60,
    )
    assert decision.actions == ()
    assert decision.decision is DecisionKind.NO_ACTION


def test_decision_uses_latest_run_instruction() -> None:
    event = _event(EventType.SHIPMENT_DELAYED)
    decision = decide(
        trigger=Trigger.SIGNAL,
        event=event,
        wake_evaluation=evaluate_wake(event),
        order_state=initial_order_state(),
        instructions=("Escalate delays immediately",),
        allowed_actions=ALLOWED,
        default_wake_minutes=60,
    )
    tools = [action.tool for action in decision.actions]
    assert BusinessAction.MESSAGE_LOGISTICS_TEAM in tools
    note = next(a for a in decision.actions if a.tool == BusinessAction.CREATE_INTERNAL_NOTE)
    assert "Escalate delays immediately" in note.arguments["note"]


def test_workflow_start_decision_schedules_a_review_without_acting() -> None:
    decision = decide(
        trigger=Trigger.WORKFLOW_START,
        event=None,
        wake_evaluation=None,
        order_state=initial_order_state(),
        instructions=(),
        allowed_actions=ALLOWED,
        default_wake_minutes=45,
    )
    assert decision.decision is DecisionKind.SLEEP
    assert decision.actions == ()
    assert decision.sleep_minutes == 45


def test_terminal_rules_are_explicit() -> None:
    assert terminal_reason_for_event(_event(EventType.DELIVERED)) is TerminalReason.DELIVERED
    assert terminal_reason_for_event(_event(EventType.PAYMENT_FAILED)) is None
    assert status_for_terminal_reason(TerminalReason.DELIVERED) is RunStatus.COMPLETED
    assert status_for_terminal_reason(TerminalReason.MANUAL_TERMINATE) is RunStatus.TERMINATED
