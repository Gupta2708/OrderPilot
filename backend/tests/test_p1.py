"""Stage 5 (P1): hybrid wake policy, human approval gate, and durability."""

import asyncio
import uuid
from dataclasses import replace
from typing import Any

from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app.agent.schema import WakeClassification
from app.domain.actions import BusinessAction
from app.domain.events import EventType, OrderEvent
from app.domain.lifecycle import RunStatus
from app.domain.wake_policy import (
    Severity,
    WakeAggressiveness,
    evaluate_fast_path,
    meets_threshold,
    needs_classification,
)
from app.temporal.activities import ClassifyRequest, ClassifyResponse, classify_event
from app.temporal.types import RunParams, workflow_id_for_order
from app.temporal.workflow import ActivityType, OrderSupervisorWorkflow
from tests.test_workflow import (
    BASE_PARAMS,
    LIFECYCLE_ACTIVITIES,
    TASK_QUEUE,
    decided_by,
    send_event,
    timeline_types,
    wait_until,
)

APPROVAL_PARAMS = replace(BASE_PARAMS, require_approval_for=[str(BusinessAction.MESSAGE_CUSTOMER)])


# ------------------------------------------------------- level A / level B


def test_routine_events_never_reach_the_classifier() -> None:
    for event_type in (EventType.PAYMENT_CONFIRMED, EventType.SHIPMENT_CREATED):
        event = OrderEvent(event_id="e", type=event_type)
        assert needs_classification(event) is False
        fast = evaluate_fast_path(event)
        assert fast is not None and fast.wake_now is False


def test_ambiguous_and_unknown_events_defer_to_the_classifier() -> None:
    for event in (
        OrderEvent(event_id="e", type=EventType.CUSTOMER_MESSAGE_RECEIVED),
        OrderEvent(event_id="e", type="warehouse_fire"),
    ):
        assert needs_classification(event) is True
        assert evaluate_fast_path(event) is None


def test_sensitivity_still_governs_the_classifier_verdict() -> None:
    assert meets_threshold(Severity.HIGH, WakeAggressiveness.BALANCED) is True
    assert meets_threshold(Severity.HIGH, WakeAggressiveness.LOW) is False
    assert meets_threshold(Severity.LOW, WakeAggressiveness.HIGH) is True


class _BrokenClassifier:
    name = "broken"

    async def decide(self, context: Any) -> Any:  # pragma: no cover - unused here
        raise RuntimeError("not used")

    async def classify(self, event: Any, order_state: Any, guidance: Any) -> WakeClassification:
        raise RuntimeError("classifier is down")


def test_classifier_failure_falls_back_to_deterministic_rules(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "app.temporal.activities.build_provider", lambda **_kwargs: _BrokenClassifier()
    )

    async def scenario() -> None:
        response = await classify_event(
            ClassifyRequest(
                event={"event_id": "e1", "type": "warehouse_fire", "payload": {}},
                order_state={},
            )
        )
        assert response.rule == "classifier_fallback_deterministic"
        # An unknown event must still be escalated, not silently dropped.
        assert response.wake_now is True

    asyncio.run(scenario())


def test_classifier_verdict_is_capped_by_wake_sensitivity(monkeypatch: Any) -> None:
    class _EagerClassifier:
        name = "eager"

        async def decide(self, context: Any) -> Any:  # pragma: no cover
            raise RuntimeError("not used")

        async def classify(self, event: Any, order_state: Any, guidance: Any):
            return WakeClassification(
                wake_now=True, severity="LOW", category="chatter", reason="Says hello."
            )

    monkeypatch.setattr(
        "app.temporal.activities.build_provider", lambda **_kwargs: _EagerClassifier()
    )

    async def scenario() -> None:
        response = await classify_event(
            ClassifyRequest(
                event={"event_id": "e1", "type": "customer_message_received", "payload": {}},
                order_state={},
                aggressiveness="BALANCED",
            )
        )
        # The classifier wanted to wake; LOW is below the BALANCED threshold.
        assert response.wake_now is False

    asyncio.run(scenario())


# --------------------------------------------------------- in-workflow use


def _classifier_stub(wake_now: bool, severity: str = "HIGH") -> Any:
    @activity.defn(name="classify_event")
    async def stub(request: ClassifyRequest) -> ClassifyResponse:
        return ClassifyResponse(
            wake_now=wake_now,
            severity=severity,
            category="customer_risk",
            reason="Classifier judged this message risky.",
            rule="ai_classifier:test",
        )

    return stub


def _activities_with(stub: Any) -> list[Any]:
    return [a for a in LIFECYCLE_ACTIVITIES if a.__name__ != "classify_event"] + [stub]


async def _start(env: WorkflowEnvironment, params: RunParams, activities: list[Any]) -> Any:
    handle = await env.client.start_workflow(
        OrderSupervisorWorkflow.run,
        params,
        id=workflow_id_for_order(f"{params.order_id}-{uuid.uuid4()}"),
        task_queue=TASK_QUEUE,
    )
    await wait_until(handle, lambda state: state["status"] != RunStatus.PENDING)
    return handle


def test_classifier_can_wake_the_agent_for_a_risky_customer_message() -> None:
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
                await send_event(handle, EventType.CUSTOMER_MESSAGE_RECEIVED, message="I cancel!")
                state = await wait_until(handle, decided_by("SIGNAL", 2))

                assert state["latest_wake_decision"]["rule"] == "ai_classifier:test"
                assert state["stats"]["classifier_calls"] == 1
                await handle.signal(OrderSupervisorWorkflow.terminate, "cleanup")
                await handle.result()
        finally:
            await env.shutdown()

    asyncio.run(scenario())


def test_classifier_can_decline_to_wake_the_agent() -> None:
    async def scenario() -> None:
        env = await WorkflowEnvironment.start_time_skipping()
        try:
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[OrderSupervisorWorkflow],
                activities=_activities_with(_classifier_stub(wake_now=False, severity="LOW")),
            ):
                handle = await _start(env, BASE_PARAMS, [])
                await send_event(handle, EventType.CUSTOMER_MESSAGE_RECEIVED, message="Thanks!")
                state = await wait_until(handle, lambda s: s["stats"]["events_received"] == 1)

                assert state["stats"]["no_wake_events"] == 1
                assert state["stats"]["agent_wakeups"] == 1  # start wake only
                await handle.signal(OrderSupervisorWorkflow.terminate, "cleanup")
                await handle.result()
        finally:
            await env.shutdown()

    asyncio.run(scenario())


# ------------------------------------------------------------- approvals


def test_sensitive_action_waits_for_approval_then_executes() -> None:
    async def scenario() -> None:
        env = await WorkflowEnvironment.start_time_skipping()
        try:
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[OrderSupervisorWorkflow],
                activities=_activities_with(_classifier_stub(wake_now=True)),
            ):
                handle = await _start(env, APPROVAL_PARAMS, [])
                await send_event(
                    handle, EventType.CUSTOMER_MESSAGE_RECEIVED, message="Where is my order?"
                )
                state = await wait_until(handle, lambda s: bool(s["pending_approvals"]))

                assert state["status"] == RunStatus.AWAITING_APPROVAL
                approval = state["pending_approvals"][0]
                assert approval["tool"] == BusinessAction.MESSAGE_CUSTOMER
                # Nothing ran while it was pending.
                assert state["stats"]["actions_executed"] == 0

                await handle.signal(OrderSupervisorWorkflow.approve_action, approval["approval_id"])
                state = await wait_until(handle, lambda s: s["stats"]["actions_executed"] == 1)
                assert state["pending_approvals"] == []
                assert state["stats"]["approvals_granted"] == 1
                executed = [a["tool"] for a in state["executed_actions"]]
                assert BusinessAction.MESSAGE_CUSTOMER in executed

                entries = timeline_types(await handle.query(OrderSupervisorWorkflow.timeline, 100))
                assert ActivityType.ACTION_PENDING_APPROVAL in entries
                assert ActivityType.ACTION_APPROVED in entries

                await handle.signal(OrderSupervisorWorkflow.terminate, "cleanup")
                await handle.result()
        finally:
            await env.shutdown()

    asyncio.run(scenario())


def test_rejected_action_is_never_executed() -> None:
    async def scenario() -> None:
        env = await WorkflowEnvironment.start_time_skipping()
        try:
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[OrderSupervisorWorkflow],
                activities=_activities_with(_classifier_stub(wake_now=True)),
            ):
                handle = await _start(env, APPROVAL_PARAMS, [])
                await send_event(
                    handle, EventType.CUSTOMER_MESSAGE_RECEIVED, message="Where is my order?"
                )
                state = await wait_until(handle, lambda s: bool(s["pending_approvals"]))
                approval = state["pending_approvals"][0]

                await handle.signal(
                    OrderSupervisorWorkflow.reject_action,
                    args=[approval["approval_id"], "Too soon"],
                )
                state = await wait_until(handle, lambda s: not s["pending_approvals"])

                assert state["stats"]["approvals_denied"] == 1
                assert state["stats"]["actions_executed"] == 0
                assert state["executed_actions"] == []
                entries = timeline_types(await handle.query(OrderSupervisorWorkflow.timeline, 100))
                assert ActivityType.ACTION_DENIED in entries
                assert ActivityType.ACTION_EXECUTED not in entries

                await handle.signal(OrderSupervisorWorkflow.terminate, "cleanup")
                await handle.result()
        finally:
            await env.shutdown()

    asyncio.run(scenario())


def test_actions_without_an_approval_requirement_still_execute_directly() -> None:
    async def scenario() -> None:
        env = await WorkflowEnvironment.start_time_skipping()
        try:
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[OrderSupervisorWorkflow],
                activities=_activities_with(_classifier_stub(wake_now=True)),
            ):
                handle = await _start(env, APPROVAL_PARAMS, [])
                # message_logistics_team is not on the approval list.
                await send_event(handle, EventType.SHIPMENT_DELAYED, reason="storm")
                state = await wait_until(handle, lambda s: s["stats"]["actions_executed"] >= 1)

                assert state["pending_approvals"] == []
                await handle.signal(OrderSupervisorWorkflow.terminate, "cleanup")
                await handle.result()
        finally:
            await env.shutdown()

    asyncio.run(scenario())


# ------------------------------------------------------------ durability


def test_run_survives_a_worker_restart_while_sleeping() -> None:
    """The durability demonstration: no worker exists for part of the run."""

    async def scenario() -> None:
        # A real dev server, not the time-skipping one: this test deliberately
        # leaves the task queue unattended, which the time-skipping server
        # cannot represent because it waits for workflow progress.
        env = await WorkflowEnvironment.start_local()
        try:
            activities = _activities_with(_classifier_stub(wake_now=True))

            # First worker: start the run, then shut the worker down entirely.
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[OrderSupervisorWorkflow],
                activities=activities,
            ):
                handle = await _start(env, BASE_PARAMS, [])
                await send_event(handle, EventType.PAYMENT_CONFIRMED)
                before = await wait_until(handle, lambda s: s["stats"]["events_received"] == 1)
                assert before["status"] == RunStatus.SLEEPING

            # No worker is running here. The event is accepted regardless:
            # Temporal holds it durably until a worker returns. Time skipping is
            # pinned so the idle gap does not fast-forward past the run's age.
            await send_event(handle, EventType.SHIPMENT_DELAYED, reason="storm")

            # Second worker: a fresh process picks the run up mid-flight.
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[OrderSupervisorWorkflow],
                activities=activities,
            ):
                after = await wait_until(handle, decided_by("SIGNAL", 2))
                assert after["order_state"]["shipment"]["status"] == "delayed"
                assert after["stats"]["events_received"] == 2
                # Memory and history from before the restart are intact.
                assert "Supervision started" in after["memory_summary"]

                await send_event(handle, EventType.DELIVERED)
                result = await handle.result()
                assert result.status == RunStatus.COMPLETED
                assert result.stats["events_received"] == 3
        finally:
            await env.shutdown()

    asyncio.run(scenario())


def test_run_keeps_supervising_when_persistence_fails() -> None:
    """Postgres is the product mirror, not the execution truth.

    A failing persistence Activity must not stop the supervisor, and must not
    spin the run loop either.
    """

    @activity.defn(name="persist_snapshot")
    async def failing_persist(request: Any) -> int:
        raise RuntimeError("database is unavailable")

    async def scenario() -> None:
        env = await WorkflowEnvironment.start_time_skipping()
        try:
            activities = [
                a
                for a in _activities_with(_classifier_stub(wake_now=True))
                if a.__name__ != "noop_persist"
            ] + [failing_persist]
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[OrderSupervisorWorkflow],
                activities=activities,
            ):
                handle = await _start(env, BASE_PARAMS, [])
                await send_event(handle, EventType.SHIPMENT_DELAYED, reason="storm")
                state = await wait_until(handle, decided_by("SIGNAL", 2))

                # The run carried on: decision made, action executed, state advanced.
                assert state["order_state"]["shipment"]["status"] == "delayed"
                assert state["stats"]["actions_executed"] >= 1
                assert state["stats"]["persist_failures"] >= 1

                # And it still completes normally.
                await send_event(handle, EventType.DELIVERED)
                result = await handle.result()
                assert result.status == RunStatus.COMPLETED
        finally:
            await env.shutdown()

    asyncio.run(scenario())
