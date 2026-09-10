"""Run lifecycle endpoints: creation, inspection, events, instructions, controls."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status

from app import repository
from app.api.deps import SessionDep, TemporalDep
from app.api.schemas import (
    ActivityResponse,
    ApprovalDecision,
    ControlResponse,
    EventAccepted,
    EventCreate,
    InstructionCreate,
    RunAnalytics,
    RunCreate,
    RunDetail,
    RunStateResponse,
    RunSummary,
    TerminateRequest,
)
from app.models import Run
from app.services import runs as run_service

router = APIRouter(prefix="/api/runs", tags=["runs"])

TIMELINE_LIMIT = 200


async def _load_run(session: SessionDep, run_id: uuid.UUID) -> Run:
    try:
        return await repository.get_run(session, run_id)
    except repository.NotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


def _unavailable(error: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))


@router.post("", response_model=RunSummary, status_code=status.HTTP_201_CREATED)
async def create_run(payload: RunCreate, session: SessionDep, client: TemporalDep) -> RunSummary:
    """Create the run and start exactly one workflow for the order."""
    try:
        run = await run_service.start_run(
            session,
            client,
            run_service.StartRunRequest(
                order_id=payload.order_id,
                supervisor_id=payload.supervisor_id,
                order_context=payload.order_context,
                initial_instructions=payload.initial_instructions,
                default_wake_minutes=payload.default_wake_minutes,
                max_age_minutes=payload.max_age_minutes,
            ),
        )
    except repository.NotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except repository.ConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except run_service.WorkflowUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error
    return RunSummary.model_validate(run)


@router.get("", response_model=list[RunSummary])
async def list_runs(
    session: SessionDep, status_filter: str | None = Query(default=None, alias="status")
) -> list[RunSummary]:
    records = await repository.list_runs(session, status=status_filter)
    return [RunSummary.model_validate(record) for record in records]


@router.get("/{run_id}", response_model=RunDetail)
async def get_run(run_id: uuid.UUID, session: SessionDep) -> RunDetail:
    """The persisted product record: state, memory, timeline, and final output."""
    run = await _load_run(session, run_id)
    activities = await repository.get_activities(session, run_id, limit=TIMELINE_LIMIT)
    return RunDetail(
        id=run.id,
        order_id=run.order_id,
        supervisor_id=run.supervisor_id,
        temporal_workflow_id=run.temporal_workflow_id,
        status=run.status,
        next_wake_at=run.next_wake_at,
        last_wake_at=run.last_wake_at,
        stats=run.stats,
        created_at=run.created_at,
        completed_at=run.completed_at,
        order_state=run.order_state,
        wake_guidance=run.wake_guidance,
        memory_summary=run.memory_summary,
        run_instructions=run.run_instructions,
        latest_decision=run.latest_decision,
        final_output=run.final_output,
        timeline=[ActivityResponse.model_validate(item) for item in activities],
    )


@router.get("/{run_id}/analytics", response_model=RunAnalytics)
async def get_run_analytics(run_id: uuid.UUID, session: SessionDep) -> RunAnalytics:
    """Counters for one run, plus the two ratios worth reading at a glance."""
    run = await _load_run(session, run_id)
    stats = run.stats or {}
    events = int(stats.get("events_received", 0))
    wakeups = int(stats.get("agent_wakeups", 0))
    actions = int(stats.get("actions_executed", 0))
    duration = int(stats.get("duration_seconds", 0))
    if not duration:
        end = run.completed_at or datetime.now(UTC)
        duration = max(0, int((end - run.created_at).total_seconds()))

    # Signal-driven wakes only: the start wake and scheduled reviews are not
    # event responses, so including them would overstate the wake rate.
    signal_wakes = max(0, wakeups - 1 - int(stats.get("scheduled_reviews", 0)))
    return RunAnalytics(
        run_id=run.id,
        order_id=run.order_id,
        status=run.status,
        events_received=events,
        agent_wakeups=wakeups,
        no_wake_events=int(stats.get("no_wake_events", 0)),
        classifier_calls=int(stats.get("classifier_calls", 0)),
        scheduled_reviews=int(stats.get("scheduled_reviews", 0)),
        actions_executed=actions,
        customer_actions=int(stats.get("customer_actions", 0)),
        approvals_granted=int(stats.get("approvals_granted", 0)),
        approvals_denied=int(stats.get("approvals_denied", 0)),
        continuations=int(stats.get("continuations", 0)),
        duration_seconds=duration,
        wake_rate=round(signal_wakes / events, 3) if events else 0.0,
        actions_per_wake=round(actions / wakeups, 2) if wakeups else 0.0,
    )


@router.get("/{run_id}/state", response_model=RunStateResponse)
async def get_run_state(
    run_id: uuid.UUID, session: SessionDep, client: TemporalDep
) -> RunStateResponse:
    """Live workflow state, falling back to the persisted snapshot."""
    run = await _load_run(session, run_id)
    live = await run_service.live_state(client, run)
    if live is not None:
        return RunStateResponse(
            run_id=run.id,
            order_id=run.order_id,
            source="workflow",
            final_output=run.final_output,
            **{key: value for key, value in live.items() if key not in {"run_id", "order_id"}},
        )
    return RunStateResponse(
        run_id=run.id,
        order_id=run.order_id,
        source="database",
        status=run.status,
        terminal=run.completed_at is not None,
        order_state=run.order_state,
        wake_guidance=run.wake_guidance,
        memory_summary=run.memory_summary,
        run_instructions=run.run_instructions,
        latest_decision=run.latest_decision,
        next_wake_at=run.next_wake_at.isoformat() if run.next_wake_at else None,
        last_wake_at=run.last_wake_at.isoformat() if run.last_wake_at else None,
        stats=run.stats,
        final_output=run.final_output,
    )


@router.post("/{run_id}/events", response_model=EventAccepted, status_code=status.HTTP_202_ACCEPTED)
async def post_event(
    run_id: uuid.UUID, payload: EventCreate, session: SessionDep, client: TemporalDep
) -> EventAccepted:
    """Deliver a lifecycle event as a Signal. Repeated event_ids are ignored."""
    run = await _load_run(session, run_id)
    try:
        event_id = await run_service.send_event(
            client, run, payload.type, payload.payload, payload.event_id
        )
    except run_service.WorkflowUnavailableError as error:
        raise _unavailable(error) from error
    return EventAccepted(event_id=event_id)


@router.post(
    "/{run_id}/instructions", response_model=ControlResponse, status_code=status.HTTP_202_ACCEPTED
)
async def post_instruction(
    run_id: uuid.UUID, payload: InstructionCreate, session: SessionDep, client: TemporalDep
) -> ControlResponse:
    run = await _load_run(session, run_id)
    try:
        await run_service.add_instruction(client, run, payload.instruction)
    except run_service.WorkflowUnavailableError as error:
        raise _unavailable(error) from error
    return ControlResponse(run_id=run.id, status=run.status)


@router.post(
    "/{run_id}/pause", response_model=ControlResponse, status_code=status.HTTP_202_ACCEPTED
)
async def pause_run(run_id: uuid.UUID, session: SessionDep, client: TemporalDep) -> ControlResponse:
    run = await _load_run(session, run_id)
    try:
        await run_service.pause(client, run)
    except run_service.WorkflowUnavailableError as error:
        raise _unavailable(error) from error
    return ControlResponse(run_id=run.id, status="PAUSING")


@router.post(
    "/{run_id}/resume", response_model=ControlResponse, status_code=status.HTTP_202_ACCEPTED
)
async def resume_run(
    run_id: uuid.UUID, session: SessionDep, client: TemporalDep
) -> ControlResponse:
    run = await _load_run(session, run_id)
    try:
        await run_service.resume(client, run)
    except run_service.WorkflowUnavailableError as error:
        raise _unavailable(error) from error
    return ControlResponse(run_id=run.id, status="RESUMING")


@router.post(
    "/{run_id}/approvals/{approval_id}/approve",
    response_model=ControlResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def approve_action(
    run_id: uuid.UUID, approval_id: str, session: SessionDep, client: TemporalDep
) -> ControlResponse:
    """Release a pending sensitive action for execution."""
    run = await _load_run(session, run_id)
    try:
        await run_service.approve_action(client, run, approval_id)
    except run_service.WorkflowUnavailableError as error:
        raise _unavailable(error) from error
    return ControlResponse(run_id=run.id, status="APPROVING")


@router.post(
    "/{run_id}/approvals/{approval_id}/reject",
    response_model=ControlResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def reject_action(
    run_id: uuid.UUID,
    approval_id: str,
    payload: ApprovalDecision,
    session: SessionDep,
    client: TemporalDep,
) -> ControlResponse:
    """Discard a pending sensitive action. It is never executed."""
    run = await _load_run(session, run_id)
    try:
        await run_service.reject_action(client, run, approval_id, payload.reason)
    except run_service.WorkflowUnavailableError as error:
        raise _unavailable(error) from error
    return ControlResponse(run_id=run.id, status="REJECTING")


@router.post(
    "/{run_id}/terminate", response_model=ControlResponse, status_code=status.HTTP_202_ACCEPTED
)
async def terminate_run(
    run_id: uuid.UUID, payload: TerminateRequest, session: SessionDep, client: TemporalDep
) -> ControlResponse:
    run = await _load_run(session, run_id)
    try:
        await run_service.terminate(client, run, payload.reason)
    except run_service.WorkflowUnavailableError as error:
        raise _unavailable(error) from error
    return ControlResponse(run_id=run.id, status="TERMINATING")
