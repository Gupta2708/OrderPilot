"""Agent runtime tests: schema validation, allow-list, memory, and fallback."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from app.agent.execution import MAX_MEMORY_LINES, compact_memory, execute_action
from app.agent.prompt import AgentContext, build_user_prompt
from app.agent.provider import MockProvider, build_provider, deterministic_fallback
from app.agent.schema import (
    MAX_SLEEP_MINUTES,
    AgentDecisionModel,
    normalize,
    parse_decision,
)
from app.domain.actions import ALL_ACTIONS, BusinessAction
from app.domain.decision import DecisionKind
from app.domain.order_state import initial_order_state
from app.temporal.activities import DecisionRequest, make_decision

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
ALLOWED = frozenset(ALL_ACTIONS)

VALID_DECISION: dict[str, Any] = {
    "decision": "ACT",
    "priority": "HIGH",
    "reason_summary": "Shipment is delayed and the customer is waiting.",
    "actions": [{"tool": "message_logistics_team", "arguments": {"message": "Please expedite."}}],
    "memory_update": "Escalated the delay to logistics.",
    "sleep": {"mode": "duration", "minutes": 15},
    "completion_recommended": False,
}


def _context(**overrides: Any) -> AgentContext:
    base = {
        "order_id": "ORD-1",
        "trigger": "SIGNAL",
        "base_instruction": "Supervise this order.",
        "order_state": initial_order_state(),
        "allowed_actions": list(ALL_ACTIONS),
        "default_wake_minutes": 60,
    }
    base.update(overrides)
    return AgentContext(**base)  # type: ignore[arg-type]


# ------------------------------------------------------------------ schema


def test_valid_decision_parses() -> None:
    decision = parse_decision(VALID_DECISION)
    assert decision.decision == "ACT"
    assert decision.actions[0].tool == "message_logistics_team"


def test_malformed_output_is_rejected() -> None:
    with pytest.raises(ValidationError):
        parse_decision({**VALID_DECISION, "decision": "SHUT_DOWN_EVERYTHING"})
    with pytest.raises(ValidationError):
        parse_decision({**VALID_DECISION, "priority": "SUPER_URGENT"})
    with pytest.raises(ValidationError):
        parse_decision({**VALID_DECISION, "reason_summary": ""})
    with pytest.raises(ValidationError):
        parse_decision("not json at all")


def test_invented_tool_names_are_rejected_by_the_schema() -> None:
    with pytest.raises(ValidationError):
        parse_decision(
            {**VALID_DECISION, "actions": [{"tool": "delete_database", "arguments": {}}]}
        )


def test_allow_list_drops_disallowed_tools_and_reports_them() -> None:
    decision, rejected = normalize(
        parse_decision(VALID_DECISION),
        allowed_actions=frozenset({BusinessAction.CREATE_INTERNAL_NOTE}),
        default_wake_minutes=60,
        now=NOW,
    )
    assert rejected == ["message_logistics_team"]
    assert decision.actions == ()
    # An ACT whose every tool was dropped must not stay an ACT.
    assert decision.decision is DecisionKind.NO_ACTION


def test_sleep_duration_is_clamped_to_sane_bounds() -> None:
    for minutes, expected in ((0, 1), (15, 15), (MAX_SLEEP_MINUTES * 10, MAX_SLEEP_MINUTES)):
        payload = {**VALID_DECISION, "sleep": {"mode": "duration", "minutes": min(minutes, 10080)}}
        decision, _ = normalize(
            parse_decision(payload), allowed_actions=ALLOWED, default_wake_minutes=60, now=NOW
        )
        assert decision.sleep_minutes == expected


def test_sleep_timestamp_is_converted_to_minutes() -> None:
    wake_at = (NOW + timedelta(minutes=45)).isoformat()
    decision, _ = normalize(
        parse_decision({**VALID_DECISION, "sleep": {"mode": "timestamp", "wake_at": wake_at}}),
        allowed_actions=ALLOWED,
        default_wake_minutes=60,
        now=NOW,
    )
    assert decision.sleep_minutes == 45


def test_unparsable_timestamp_falls_back_to_the_default_interval() -> None:
    decision, _ = normalize(
        parse_decision({**VALID_DECISION, "sleep": {"mode": "timestamp", "wake_at": "whenever"}}),
        allowed_actions=ALLOWED,
        default_wake_minutes=90,
        now=NOW,
    )
    assert decision.sleep_minutes == 90


# ----------------------------------------------------------------- actions


def test_each_required_action_executes() -> None:
    for tool in ALL_ACTIONS:
        outcome = execute_action(tool, {"message": "hi", "note": "hi"}, ALLOWED, "ORD-1")
        assert outcome.ok, tool
        assert "ORD-1" in outcome.detail


def test_action_execution_refuses_disallowed_and_unknown_tools() -> None:
    disallowed = execute_action(
        BusinessAction.MESSAGE_CUSTOMER,
        {"message": "hello"},
        frozenset({BusinessAction.CREATE_INTERNAL_NOTE}),
        "ORD-1",
    )
    assert disallowed.ok is False
    assert "not allowed" in disallowed.detail

    unknown = execute_action("drop_tables", {}, ALLOWED, "ORD-1")
    assert unknown.ok is False
    assert "Unknown tool" in unknown.detail


def test_missing_message_falls_back_to_a_safe_default() -> None:
    outcome = execute_action(BusinessAction.MESSAGE_CUSTOMER, {}, ALLOWED, "ORD-1")
    assert outcome.ok is True
    assert outcome.arguments["message"]


# ------------------------------------------------------------------ memory


def test_memory_compaction_caps_lines_and_marks_what_was_dropped() -> None:
    updates = [f"note {i}" for i in range(MAX_MEMORY_LINES + 5)]
    summary = compact_memory("", updates)
    lines = summary.splitlines()
    assert len(lines) == MAX_MEMORY_LINES + 1  # kept lines plus the compaction marker
    assert "compacted" in lines[0]
    assert lines[-1] == updates[-1]


def test_memory_compaction_skips_consecutive_duplicates() -> None:
    summary = compact_memory("same note", ["same note"])
    assert summary == "same note"


# --------------------------------------------------------------- providers


def test_mock_provider_is_deterministic_and_needs_no_key() -> None:
    async def scenario() -> None:
        provider = MockProvider()
        context = _context(
            triggering_event={"event_id": "e1", "type": "shipment_delayed", "payload": {}}
        )
        first = await provider.decide(context)
        second = await provider.decide(context)
        assert first == second
        assert first.actions[0].tool == BusinessAction.MESSAGE_LOGISTICS_TEAM

    asyncio.run(scenario())


def test_default_provider_is_the_mock() -> None:
    assert build_provider("mock", "claude-opus-5", None).name == "mock"
    assert build_provider("anything-else", "claude-opus-5", None).name == "mock"


def test_deterministic_fallback_never_acts() -> None:
    fallback = deterministic_fallback(_context())
    assert fallback.decision == "NO_ACTION"
    assert fallback.actions == []


def test_prompt_contains_context_but_not_raw_history() -> None:
    prompt = build_user_prompt(
        _context(
            run_instructions=["Escalate delays immediately"],
            memory_summary="Payment confirmed.",
            triggering_event={"event_id": "e1", "type": "shipment_delayed", "payload": {}},
        )
    )
    assert "Escalate delays immediately" in prompt
    assert "Payment confirmed." in prompt
    assert "shipment_delayed" in prompt
    assert "message_customer" in prompt  # allowed actions are listed


# -------------------------------------------------------------- activities


class _BrokenProvider:
    name = "broken"

    async def decide(self, context: AgentContext) -> AgentDecisionModel:
        raise RuntimeError("provider is down")


def test_decision_activity_degrades_safely_when_the_provider_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.temporal.activities.build_provider", lambda **_kwargs: _BrokenProvider()
    )

    async def scenario() -> None:
        response = await make_decision(
            DecisionRequest(
                order_id="ORD-1",
                trigger="SIGNAL",
                base_instruction="Supervise this order.",
                allowed_actions=list(ALL_ACTIONS),
                default_wake_minutes=30,
            )
        )
        assert response.fallback_used is True
        assert response.provider == "fallback"
        assert response.decision == "NO_ACTION"
        assert response.actions == []
        assert response.sleep_minutes == 30

    asyncio.run(scenario())


def test_decision_activity_enforces_the_allow_list_end_to_end() -> None:
    async def scenario() -> None:
        response = await make_decision(
            DecisionRequest(
                order_id="ORD-1",
                trigger="SIGNAL",
                base_instruction="Supervise this order.",
                triggering_event={"event_id": "e1", "type": "shipment_delayed", "payload": {}},
                allowed_actions=[BusinessAction.CREATE_INTERNAL_NOTE],
                default_wake_minutes=30,
            )
        )
        tools = [action["tool"] for action in response.actions]
        assert BusinessAction.MESSAGE_LOGISTICS_TEAM not in tools

    asyncio.run(scenario())
