"""Temporal lifecycle tests.

These run against the Temporal test server with time skipping, so durable
timers are exercised without waiting in real time. The test server binary is
downloaded on first use.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Any

from temporalio.client import WorkflowHandle
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app.domain.actions import BusinessAction
from app.domain.events import EventType
from app.domain.lifecycle import RunStatus, TerminalReason
from app.temporal.types import RunParams, RunResult, workflow_id_for_order
from app.temporal.workflow import ActivityType, OrderSupervisorWorkflow

TASK_QUEUE = "orderpilot-test"

BASE_PARAMS = RunParams(
    run_id="run-1",
    order_id="ORD-1",
    default_wake_minutes=30,
    max_age_minutes=7 * 24 * 60,
)


@asynccontextmanager
async def running_workflow(
    params: RunParams,
) -> AsyncIterator[tuple[WorkflowEnvironment, WorkflowHandle[Any, RunResult]]]:
    """Start one supervisor workflow on a time-skipping test environment."""
    env = await WorkflowEnvironment.start_time_skipping()
    try:
        async with Worker(env.client, task_queue=TASK_QUEUE, workflows=[OrderSupervisorWorkflow]):
            handle: WorkflowHandle[Any, RunResult] = await env.client.start_workflow(
                OrderSupervisorWorkflow.run,
                params,
                id=workflow_id_for_order(f"{params.order_id}-{uuid.uuid4()}"),
                task_queue=TASK_QUEUE,
            )
            await wait_until(handle, lambda state: state["status"] != RunStatus.PENDING)
            yield env, handle
    finally:
        await env.shutdown()


async def wait_until(
    handle: WorkflowHandle[Any, RunResult],
    predicate: Callable[[dict[str, Any]], bool],
    attempts: int = 100,
) -> dict[str, Any]:
    """Poll the workflow Query until the predicate holds."""
    state: dict[str, Any] = {}
    for _ in range(attempts):
        state = await handle.query(OrderSupervisorWorkflow.state)
        if predicate(state):
            return state
        await asyncio.sleep(0.05)
    raise AssertionError(f"condition never became true; last state: {state}")


async def send_event(
    handle: WorkflowHandle[Any, RunResult],
    event_type: str,
    event_id: str | None = None,
    **payload: Any,
) -> None:
    await handle.signal(
        OrderSupervisorWorkflow.order_event,
        {
            "event_id": event_id or f"evt-{uuid.uuid4()}",
            "type": event_type,
            "payload": dict(payload),
        },
    )


def timeline_types(entries: list[dict[str, Any]]) -> list[str]:
    return [entry["type"] for entry in entries]


def test_workflow_start_wakes_the_agent_and_schedules_a_durable_sleep() -> None:
    async def scenario() -> None:
        async with running_workflow(BASE_PARAMS) as (_env, handle):
            state = await handle.query(OrderSupervisorWorkflow.state)
            assert state["status"] == RunStatus.SLEEPING
            assert state["stats"]["agent_wakeups"] == 1
            assert state["next_wake_at"] is not None
            assert state["latest_decision"]["trigger"] == "WORKFLOW_START"

            entries = timeline_types(await handle.query(OrderSupervisorWorkflow.timeline))
            assert ActivityType.RUN_STARTED in entries
            assert ActivityType.AGENT_DECISION in entries
            assert ActivityType.SLEEP_SCHEDULED in entries

            await handle.signal(OrderSupervisorWorkflow.terminate, "test cleanup")
            await handle.result()

    asyncio.run(scenario())


def test_routine_event_updates_state_without_waking_the_agent() -> None:
    async def scenario() -> None:
        async with running_workflow(BASE_PARAMS) as (_env, handle):
            await send_event(handle, EventType.PAYMENT_CONFIRMED)
            state = await wait_until(handle, lambda s: s["stats"]["events_received"] == 1)

            assert state["stats"]["no_wake_events"] == 1
            assert state["stats"]["agent_wakeups"] == 1  # still only the start wake
            assert state["order_state"]["payment"]["status"] == "confirmed"
            assert state["latest_wake_decision"]["wake_now"] is False

            await handle.signal(OrderSupervisorWorkflow.terminate, "test cleanup")
            await handle.result()

    asyncio.run(scenario())


def test_important_signal_wakes_the_agent_immediately() -> None:
    async def scenario() -> None:
        async with running_workflow(BASE_PARAMS) as (_env, handle):
            await send_event(handle, EventType.SHIPMENT_DELAYED, reason="storm")
            state = await wait_until(handle, lambda s: s["stats"]["agent_wakeups"] == 2)

            assert state["latest_wake_decision"]["wake_now"] is True
            assert state["latest_decision"]["trigger"] == "SIGNAL"
            assert state["latest_decision"]["priority"] == "HIGH"
            tools = [action["tool"] for action in state["latest_decision"]["actions"]]
            assert BusinessAction.MESSAGE_LOGISTICS_TEAM in tools
            assert state["order_state"]["shipment"]["status"] == "delayed"

            await handle.signal(OrderSupervisorWorkflow.terminate, "test cleanup")
            await handle.result()

    asyncio.run(scenario())


def test_duplicate_event_is_ignored() -> None:
    async def scenario() -> None:
        async with running_workflow(BASE_PARAMS) as (_env, handle):
            await send_event(handle, EventType.PAYMENT_CONFIRMED, event_id="dup-1")
            await wait_until(handle, lambda s: s["stats"]["events_received"] == 1)
            await send_event(handle, EventType.PAYMENT_CONFIRMED, event_id="dup-1")

            entries = timeline_types(await handle.query(OrderSupervisorWorkflow.timeline, 100))
            assert ActivityType.EVENT_DUPLICATE_IGNORED in entries
            state = await handle.query(OrderSupervisorWorkflow.state)
            assert state["stats"]["events_received"] == 1

            await handle.signal(OrderSupervisorWorkflow.terminate, "test cleanup")
            await handle.result()

    asyncio.run(scenario())


def test_malformed_event_is_rejected_without_breaking_the_run() -> None:
    async def scenario() -> None:
        async with running_workflow(BASE_PARAMS) as (_env, handle):
            await handle.signal(OrderSupervisorWorkflow.order_event, {"type": "delivered"})
            entries = timeline_types(await handle.query(OrderSupervisorWorkflow.timeline, 100))
            assert ActivityType.EVENT_REJECTED in entries

            state = await handle.query(OrderSupervisorWorkflow.state)
            assert state["terminal"] is False
            assert state["stats"]["events_received"] == 0

            await handle.signal(OrderSupervisorWorkflow.terminate, "test cleanup")
            await handle.result()

    asyncio.run(scenario())


def test_durable_timer_wakes_the_agent_without_any_signal() -> None:
    async def scenario() -> None:
        params = replace(BASE_PARAMS, default_wake_minutes=30)
        async with running_workflow(params) as (env, handle):
            await env.sleep(31 * 60)
            state = await wait_until(handle, lambda s: s["stats"]["scheduled_reviews"] >= 1)

            assert state["stats"]["agent_wakeups"] >= 2
            assert state["latest_decision"]["trigger"] == "SCHEDULED_TIMER"

            await handle.signal(OrderSupervisorWorkflow.terminate, "test cleanup")
            await handle.result()

    asyncio.run(scenario())


def test_pause_defers_events_and_resume_processes_them() -> None:
    async def scenario() -> None:
        async with running_workflow(BASE_PARAMS) as (_env, handle):
            await handle.signal(OrderSupervisorWorkflow.pause)
            paused = await wait_until(handle, lambda s: s["status"] == RunStatus.PAUSED)
            assert paused["paused"] is True

            await send_event(handle, EventType.SHIPMENT_DELAYED)
            deferred = await wait_until(handle, lambda s: s["pending_events"] == 1)
            assert deferred["stats"]["events_received"] == 0
            assert deferred["stats"]["agent_wakeups"] == 1

            await handle.signal(OrderSupervisorWorkflow.resume)
            resumed = await wait_until(handle, lambda s: s["stats"]["events_received"] == 1)
            assert resumed["status"] != RunStatus.PAUSED
            assert resumed["stats"]["agent_wakeups"] == 2

            await handle.signal(OrderSupervisorWorkflow.terminate, "test cleanup")
            await handle.result()

    asyncio.run(scenario())


def test_terminate_works_while_the_workflow_is_sleeping() -> None:
    async def scenario() -> None:
        async with running_workflow(BASE_PARAMS) as (_env, handle):
            await handle.signal(OrderSupervisorWorkflow.terminate, "operator stopped the run")
            result = await handle.result()

            assert result.status == RunStatus.TERMINATED
            assert result.terminal_reason == TerminalReason.MANUAL_TERMINATE
            assert "operator stopped the run" in result.recommendations[0]

    asyncio.run(scenario())


def test_terminate_works_while_the_workflow_is_paused() -> None:
    async def scenario() -> None:
        async with running_workflow(BASE_PARAMS) as (_env, handle):
            await handle.signal(OrderSupervisorWorkflow.pause)
            await wait_until(handle, lambda s: s["status"] == RunStatus.PAUSED)

            await handle.signal(OrderSupervisorWorkflow.terminate, "stopped while paused")
            result = await handle.result()
            assert result.status == RunStatus.TERMINATED

    asyncio.run(scenario())


def test_delivered_event_completes_the_run_with_a_final_output() -> None:
    async def scenario() -> None:
        async with running_workflow(BASE_PARAMS) as (_env, handle):
            await send_event(handle, EventType.PAYMENT_CONFIRMED)
            await wait_until(handle, lambda s: s["stats"]["events_received"] == 1)
            await send_event(handle, EventType.DELIVERED)

            result = await handle.result()
            assert result.status == RunStatus.COMPLETED
            assert result.terminal_reason == TerminalReason.DELIVERED
            assert result.order_state["delivery"]["status"] == "delivered"
            assert result.final_summary
            assert result.learnings
            assert result.recommendations
            assert result.stats["events_received"] == 2
            assert result.stats["no_wake_events"] == 1
            assert result.memory_summary

    asyncio.run(scenario())


def test_live_instruction_changes_the_next_decision() -> None:
    async def scenario() -> None:
        async with running_workflow(BASE_PARAMS) as (_env, handle):
            await handle.signal(
                OrderSupervisorWorkflow.add_instruction,
                "If shipment is delayed, escalate immediately.",
            )
            await wait_until(handle, lambda s: len(s["run_instructions"]) == 1)

            await send_event(handle, EventType.SHIPMENT_DELAYED)
            state = await wait_until(handle, lambda s: s["stats"]["agent_wakeups"] == 2)

            notes = [
                action
                for action in state["latest_decision"]["actions"]
                if action["tool"] == BusinessAction.CREATE_INTERNAL_NOTE
            ]
            assert notes and "escalate immediately" in notes[0]["arguments"]["note"].lower()

            await handle.signal(OrderSupervisorWorkflow.terminate, "test cleanup")
            await handle.result()

    asyncio.run(scenario())


def test_run_ends_when_it_reaches_its_maximum_age() -> None:
    async def scenario() -> None:
        params = replace(BASE_PARAMS, default_wake_minutes=10, max_age_minutes=45)
        async with running_workflow(params) as (_env, handle):
            result = await handle.result()
            assert result.status == RunStatus.COMPLETED
            assert result.terminal_reason == TerminalReason.MAX_AGE_REACHED
            assert result.stats["scheduled_reviews"] >= 1

    asyncio.run(scenario())
