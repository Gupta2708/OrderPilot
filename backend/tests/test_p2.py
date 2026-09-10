"""Stage 6 (P2): adaptive wake guidance, Continue-As-New, and templates."""

import asyncio
from dataclasses import replace
from typing import Any

from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app.agent.schema import (
    MAX_GUIDANCE_ITEMS,
    AgentDecisionModel,
    clean_guidance,
    parse_decision,
)
from app.domain.actions import ALL_ACTIONS, BusinessAction
from app.domain.events import EventType, OrderEvent
from app.domain.lifecycle import RunStatus
from app.domain.templates import TEMPLATES, TEMPLATES_BY_KEY
from app.domain.wake_policy import WakeAggressiveness
from app.temporal.activities import ClassifyRequest, DecisionRequest, DecisionResponse
from app.temporal.workflow import (
    CARRIED_EVENT_IDS,
    ActivityType,
    OrderSupervisorWorkflow,
)
from tests.test_p1 import _activities_with, _classifier_stub, _start
from tests.test_workflow import (
    BASE_PARAMS,
    TASK_QUEUE,
    send_event,
    timeline_types,
    wait_until,
)

# ---------------------------------------------------------------- templates


def test_three_templates_are_meaningfully_different() -> None:
    assert {t.key for t in TEMPLATES} == {"standard", "vip", "cost_conscious"}

    standard = TEMPLATES_BY_KEY["standard"]
    vip = TEMPLATES_BY_KEY["vip"]
    thrifty = TEMPLATES_BY_KEY["cost_conscious"]

    # VIP wakes most readily and reviews most often.
    assert vip.wake_aggressiveness == WakeAggressiveness.HIGH
    assert standard.wake_aggressiveness == WakeAggressiveness.BALANCED
    assert thrifty.wake_aggressiveness == WakeAggressiveness.LOW
    assert vip.default_wake_minutes < standard.default_wake_minutes < thrifty.default_wake_minutes

    # The cost-conscious policy cannot message the customer at all.
    assert BusinessAction.MESSAGE_CUSTOMER not in thrifty.allowed_actions
    assert BusinessAction.MESSAGE_CUSTOMER in vip.allowed_actions

    # Standard holds customer contact for a human; VIP is trusted to send.
    assert standard.require_approval_for == [str(BusinessAction.MESSAGE_CUSTOMER)]
    assert vip.require_approval_for == []


def test_templates_only_reference_real_actions() -> None:
    for template in TEMPLATES:
        assert set(template.allowed_actions) <= set(ALL_ACTIONS)
        assert set(template.require_approval_for) <= set(template.allowed_actions)


# ----------------------------------------------------------- wake guidance


def test_guidance_is_bounded_and_deduplicated() -> None:
    cleaned = clean_guidance(
        [
            "  Treat   any further delay as critical ",
            "Treat any further delay as critical",
            "",
            "x" * 500,
            "Second hint",
            "Third hint",
            "Fourth hint should be dropped",
        ]
    )
    assert len(cleaned) <= MAX_GUIDANCE_ITEMS
    assert cleaned[0] == "Treat any further delay as critical"
    assert all(len(line) <= 200 for line in cleaned)
    assert "Fourth hint should be dropped" not in cleaned


def test_decision_without_guidance_defaults_to_none() -> None:
    decision = parse_decision(
        {
            "decision": "NO_ACTION",
            "priority": "LOW",
            "reason_summary": "Nothing to do.",
        }
    )
    assert decision.wake_guidance == []
    # An omitted opinion must not read as a recommendation to finish the run.
    assert decision.completion_recommended is False


def _guidance_provider(guidance: list[str]) -> Any:
    """A decision Activity that emits standing guidance on the first wake."""
    seen: list[int] = []

    @activity.defn(name="make_decision")
    async def stub(request: DecisionRequest) -> DecisionResponse:
        seen.append(1)
        return DecisionResponse(
            decision="NO_ACTION",
            priority="LOW",
            reason_summary="Watching this order.",
            actions=[],
            memory_update="Reviewed.",
            sleep_minutes=30,
            completion_recommended=False,
            provider="stub",
            wake_guidance=guidance if len(seen) == 1 else [],
        )

    return stub


def test_agent_guidance_is_recorded_and_reaches_the_classifier() -> None:
    seen_guidance: list[list[str]] = []

    @activity.defn(name="classify_event")
    async def capturing_classifier(request: ClassifyRequest) -> Any:
        from app.temporal.activities import ClassifyResponse

        seen_guidance.append(list(request.wake_guidance))
        return ClassifyResponse(
            wake_now=False,
            severity="LOW",
            category="routine",
            reason="Routine.",
            rule="ai_classifier:test",
        )

    async def scenario() -> None:
        env = await WorkflowEnvironment.start_time_skipping()
        try:
            activities = [
                a for a in _activities_with(capturing_classifier) if a.__name__ != "make_decision"
            ] + [_guidance_provider(["Treat any further delay as critical."])]
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[OrderSupervisorWorkflow],
                activities=activities,
            ):
                handle = await _start(env, BASE_PARAMS, [])
                state = await wait_until(handle, lambda s: bool(s["wake_guidance"]))
                assert state["wake_guidance"] == ["Treat any further delay as critical."]

                entries = timeline_types(await handle.query(OrderSupervisorWorkflow.timeline, 100))
                assert ActivityType.WAKE_GUIDANCE_UPDATED in entries

                # An ambiguous event must carry that guidance into triage.
                await send_event(handle, EventType.CUSTOMER_MESSAGE_RECEIVED, message="Hello")
                # The counter increments before triage runs, so wait for the
                # verdict itself rather than for the event count.
                verdict = await wait_until(handle, lambda s: s["latest_wake_decision"] is not None)
                assert verdict["latest_wake_decision"]["rule"] == "ai_classifier:test"
                assert seen_guidance
                assert seen_guidance[-1] == ["Treat any further delay as critical."]

                await handle.signal(OrderSupervisorWorkflow.terminate, "cleanup")
                await handle.result()
        finally:
            await env.shutdown()

    asyncio.run(scenario())


def test_guidance_cannot_widen_the_allow_list() -> None:
    """Guidance advises triage; it must never grant new powers."""
    from datetime import UTC, datetime

    from app.agent.schema import normalize

    decision = AgentDecisionModel(
        decision="ACT",
        priority="HIGH",
        reason_summary="Guidance says contact the customer.",
        actions=[{"tool": "message_customer", "arguments": {"message": "hi"}}],  # type: ignore[list-item]
        wake_guidance=["Always message the customer directly."],
    )
    resolved, rejected = normalize(
        decision,
        allowed_actions=frozenset({BusinessAction.CREATE_INTERNAL_NOTE}),
        default_wake_minutes=60,
        now=datetime.now(UTC),
    )
    assert resolved.actions == ()
    assert rejected == ["message_customer"]


# ------------------------------------------------------- continue-as-new


def test_continue_as_new_preserves_the_run_across_history_reset() -> None:
    async def scenario() -> None:
        env = await WorkflowEnvironment.start_time_skipping()
        try:
            params = replace(
                BASE_PARAMS,
                order_id="ORD-CAN",
                continue_as_new_after_events=2,
                default_wake_minutes=120,
            )
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[OrderSupervisorWorkflow],
                activities=_activities_with(_classifier_stub(wake_now=True)),
            ):
                handle = await _start(env, params, [])

                await send_event(handle, EventType.PAYMENT_CONFIRMED)
                await send_event(handle, EventType.SHIPMENT_DELAYED, reason="storm")
                state = await wait_until(handle, lambda s: s["stats"].get("continuations", 0) >= 1)

                # Same logical run, same order, and nothing lost.
                assert state["order_id"] == "ORD-CAN"
                assert state["stats"]["events_received"] == 2
                assert state["order_state"]["shipment"]["status"] == "delayed"
                assert state["order_state"]["payment"]["status"] == "confirmed"
                assert state["memory_summary"]
                assert state["stats"]["actions_executed"] >= 1
                assert state["status"] != RunStatus.PENDING

                # The continuation keeps working and still completes normally.
                await send_event(handle, EventType.DELIVERED)
                result = await handle.result()
                assert result.status == RunStatus.COMPLETED
                assert result.order_id == "ORD-CAN"
                assert result.stats["events_received"] == 3
                assert result.stats["continuations"] >= 1
        finally:
            await env.shutdown()

    asyncio.run(scenario())


def test_continue_as_new_does_not_re_run_the_start_wake() -> None:
    async def scenario() -> None:
        env = await WorkflowEnvironment.start_time_skipping()
        try:
            params = replace(
                BASE_PARAMS,
                order_id="ORD-CAN2",
                continue_as_new_after_events=1,
                default_wake_minutes=120,
            )
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[OrderSupervisorWorkflow],
                activities=_activities_with(_classifier_stub(wake_now=True)),
            ):
                handle = await _start(env, params, [])
                await send_event(handle, EventType.SHIPMENT_DELAYED, reason="storm")
                state = await wait_until(handle, lambda s: s["stats"].get("continuations", 0) >= 1)

                # One start wake plus one signal wake: the continuation adds none.
                assert state["stats"]["agent_wakeups"] == 2
                assert state["latest_decision"]["trigger"] == "SIGNAL"

                await handle.signal(OrderSupervisorWorkflow.terminate, "cleanup")
                await handle.result()
        finally:
            await env.shutdown()

    asyncio.run(scenario())


def test_continue_as_new_waits_for_a_pending_approval() -> None:
    """A run must not reset history while a human still owes it a decision."""

    async def scenario() -> None:
        env = await WorkflowEnvironment.start_time_skipping()
        try:
            params = replace(
                BASE_PARAMS,
                order_id="ORD-CAN3",
                continue_as_new_after_events=1,
                require_approval_for=[str(BusinessAction.MESSAGE_CUSTOMER)],
                default_wake_minutes=120,
            )
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[OrderSupervisorWorkflow],
                activities=_activities_with(_classifier_stub(wake_now=True)),
            ):
                handle = await _start(env, params, [])
                await send_event(
                    handle, EventType.CUSTOMER_MESSAGE_RECEIVED, message="Where is my order?"
                )
                state = await wait_until(handle, lambda s: bool(s["pending_approvals"]))

                # Threshold reached, but the approval blocks the continuation.
                assert state["stats"].get("continuations", 0) == 0

                approval = state["pending_approvals"][0]
                await handle.signal(OrderSupervisorWorkflow.approve_action, approval["approval_id"])
                state = await wait_until(handle, lambda s: s["stats"].get("continuations", 0) >= 1)
                assert state["pending_approvals"] == []

                await handle.signal(OrderSupervisorWorkflow.terminate, "cleanup")
                await handle.result()
        finally:
            await env.shutdown()

    asyncio.run(scenario())


def test_continue_as_new_is_off_by_default() -> None:
    async def scenario() -> None:
        env = await WorkflowEnvironment.start_time_skipping()
        try:
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[OrderSupervisorWorkflow],
                activities=_activities_with(_classifier_stub(wake_now=True)),
            ):
                handle = await _start(env, BASE_PARAMS, [])
                for _ in range(3):
                    await send_event(handle, EventType.SHIPMENT_DELAYED, reason="storm")
                state = await wait_until(handle, lambda s: s["stats"]["events_received"] == 3)
                assert state["stats"].get("continuations", 0) == 0

                await handle.signal(OrderSupervisorWorkflow.terminate, "cleanup")
                await handle.result()
        finally:
            await env.shutdown()

    asyncio.run(scenario())


def test_carried_state_round_trip_loses_nothing() -> None:
    """Regression: queued Signals must survive the Continue-As-New boundary.

    `_persist` inside the continuation awaits, which yields and lets Signal
    handlers run, so events can be queued at the moment the run continues.
    Carrying an empty list there dropped them silently.
    """
    before = OrderSupervisorWorkflow()
    before._params = BASE_PARAMS
    before._order_state = {"payment": {"status": "confirmed"}}
    before._memory_summary = "Payment confirmed."
    before._instructions = ["Escalate delays."]
    before._wake_guidance = ["Treat further delay as critical."]
    before._stats = {"events_received": 7, "agent_wakeups": 3}
    before._executed_actions = [{"tool": "create_internal_note", "ok": True}]
    before._pending_approvals = [{"approval_id": "a1", "tool": "message_customer"}]
    before._sequence = 42
    before._continuations = 1
    # Two events queued right as the run crosses the threshold.
    before._pending_events = [
        OrderEvent(event_id="late-1", type="delivered", payload={}),
        OrderEvent(event_id="late-2", type="refund_requested", payload={"reason": "late"}),
    ]
    for index in range(120):
        before._seen_event_ids[f"seen-{index}"] = None

    carried = before._carried_state()

    assert [e["event_id"] for e in carried.pending_events] == ["late-1", "late-2"]
    # The id tail is bounded but must be the newest ids, not an arbitrary slice.
    assert len(carried.recent_event_ids) == CARRIED_EVENT_IDS
    assert carried.recent_event_ids[-1] == "seen-119"

    after = OrderSupervisorWorkflow()
    after._params = BASE_PARAMS
    after._restore(carried)

    assert [e.event_id for e in after._pending_events] == ["late-1", "late-2"]
    assert after._pending_events[1].payload == {"reason": "late"}
    assert after._order_state == before._order_state
    assert after._memory_summary == before._memory_summary
    assert after._instructions == before._instructions
    assert after._wake_guidance == before._wake_guidance
    assert after._stats == before._stats
    assert after._executed_actions == before._executed_actions
    assert after._pending_approvals == before._pending_approvals
    assert after._sequence == 42
    assert after._continuations == 1
    # De-duplication still works for a recently seen id.
    assert "seen-119" in after._seen_event_ids


def test_all_events_survive_a_run_that_continues() -> None:
    """End-to-end: a burst spanning the threshold loses nothing."""

    async def scenario() -> None:
        env = await WorkflowEnvironment.start_time_skipping()
        try:
            params = replace(
                BASE_PARAMS,
                order_id="ORD-CAN4",
                continue_as_new_after_events=1,
                default_wake_minutes=120,
            )
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[OrderSupervisorWorkflow],
                activities=_activities_with(_classifier_stub(wake_now=True)),
            ):
                handle = await _start(env, params, [])
                await send_event(handle, EventType.PAYMENT_CONFIRMED)
                await wait_until(handle, lambda s: s["stats"].get("continuations", 0) >= 1)

                await send_event(handle, EventType.SHIPMENT_DELAYED, reason="storm")
                await send_event(handle, EventType.DELIVERED)

                result = await handle.result()
                assert result.status == RunStatus.COMPLETED
                assert result.stats["events_received"] == 3
                assert result.stats["continuations"] >= 1
                assert result.order_state["delivery"]["status"] == "delivered"
        finally:
            await env.shutdown()

    asyncio.run(scenario())
