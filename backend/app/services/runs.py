"""Run orchestration: create runs, start workflows, and route controls to Signals.

Kept out of the HTTP handlers so it can be tested directly, and so the mapping
from product operations to Temporal operations lives in one place.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client, WorkflowHandle
from temporalio.service import RPCError

from app import repository
from app.config import get_settings
from app.domain.order_state import initial_order_state
from app.models import Run
from app.temporal.types import RunParams, workflow_id_for_order
from app.temporal.workflow import OrderSupervisorWorkflow


class WorkflowUnavailableError(Exception):
    """The workflow is gone or no longer accepting this operation."""


@dataclass
class StartRunRequest:
    order_id: str
    supervisor_id: uuid.UUID
    order_context: dict[str, Any]
    initial_instructions: list[str]
    default_wake_minutes: int | None = None
    max_age_minutes: int | None = None


def _handle(client: Client, run: Run) -> WorkflowHandle[Any, Any]:
    return client.get_workflow_handle(run.temporal_workflow_id)


async def start_run(session: AsyncSession, client: Client, request: StartRunRequest) -> Run:
    """Create the run record, then start exactly one workflow for the order.

    The row is written first so the workflow always has something to persist
    into. If the workflow fails to start, the transaction is rolled back by the
    caller and no orphan run is left behind.
    """
    supervisor = await repository.get_supervisor(session, request.supervisor_id)
    workflow_id = workflow_id_for_order(request.order_id)

    run = await repository.create_run(
        session,
        order_id=request.order_id,
        supervisor_id=supervisor.id,
        temporal_workflow_id=workflow_id,
        status="PENDING",
        order_state=initial_order_state(),
        run_instructions=list(request.initial_instructions),
    )

    config = supervisor.config or {}
    params = RunParams(
        run_id=str(run.id),
        order_id=request.order_id,
        supervisor_name=supervisor.name,
        base_instruction=supervisor.base_instruction,
        allowed_actions=list(supervisor.allowed_actions),
        wake_aggressiveness=str(config.get("wake_aggressiveness", "BALANCED")),
        default_wake_minutes=int(
            request.default_wake_minutes or config.get("default_wake_minutes", 60)
        ),
        max_age_minutes=int(request.max_age_minutes or config.get("max_age_minutes", 7 * 24 * 60)),
        initial_instructions=list(request.initial_instructions),
        order_context=dict(request.order_context),
    )

    try:
        await client.start_workflow(
            OrderSupervisorWorkflow.run,
            params,
            id=workflow_id,
            task_queue=get_settings().temporal_task_queue,
        )
    except Exception as error:  # noqa: BLE001 - surfaced as a clean API error
        raise WorkflowUnavailableError(f"Could not start workflow: {error}") from error
    return run


async def send_event(
    client: Client, run: Run, event_type: str, payload: dict[str, Any], event_id: str | None
) -> str:
    """Signal one lifecycle event. The workflow de-duplicates by event_id."""
    resolved_id = event_id or str(uuid.uuid4())
    await _signal(
        client,
        run,
        OrderSupervisorWorkflow.order_event,
        {"event_id": resolved_id, "type": event_type, "payload": dict(payload)},
    )
    return resolved_id


async def add_instruction(client: Client, run: Run, instruction: str) -> None:
    await _signal(client, run, OrderSupervisorWorkflow.add_instruction, instruction)


async def pause(client: Client, run: Run) -> None:
    await _signal(client, run, OrderSupervisorWorkflow.pause)


async def resume(client: Client, run: Run) -> None:
    await _signal(client, run, OrderSupervisorWorkflow.resume)


async def terminate(client: Client, run: Run, reason: str) -> None:
    await _signal(client, run, OrderSupervisorWorkflow.terminate, reason)


async def _signal(client: Client, run: Run, signal: Any, *args: Any) -> None:
    try:
        await _handle(client, run).signal(signal, *args)
    except RPCError as error:
        raise WorkflowUnavailableError(
            f"Run {run.id} is no longer accepting signals: {error.message}"
        ) from error


async def live_state(client: Client, run: Run) -> dict[str, Any] | None:
    """Query the workflow for authoritative live state.

    Returns None when the workflow is gone, so callers can fall back to the
    persisted snapshot rather than failing the request.
    """
    try:
        result: dict[str, Any] = await _handle(client, run).query(OrderSupervisorWorkflow.state)
    except (RPCError, RuntimeError):
        return None
    return result
