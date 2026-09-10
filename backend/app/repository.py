"""Database access for supervisors, runs, and the unified activity timeline.

Plain async functions over an AsyncSession so the business logic stays testable
without HTTP handlers or Temporal.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ActivityRecord, Run, Supervisor


class ConflictError(Exception):
    """A uniqueness rule would be violated (for example a duplicate order)."""


class NotFoundError(Exception):
    """The requested record does not exist."""


# ------------------------------------------------------------- supervisors


async def create_supervisor(
    session: AsyncSession,
    name: str,
    base_instruction: str,
    allowed_actions: list[str],
    config: dict[str, Any],
) -> Supervisor:
    supervisor = Supervisor(
        name=name,
        base_instruction=base_instruction,
        allowed_actions=list(allowed_actions),
        config=dict(config),
    )
    session.add(supervisor)
    await session.flush()
    await session.refresh(supervisor)
    return supervisor


async def list_supervisors(session: AsyncSession) -> list[Supervisor]:
    result = await session.scalars(select(Supervisor).order_by(Supervisor.created_at))
    return list(result)


async def get_supervisor(session: AsyncSession, supervisor_id: uuid.UUID) -> Supervisor:
    supervisor = await session.get(Supervisor, supervisor_id)
    if supervisor is None:
        raise NotFoundError(f"Supervisor {supervisor_id} not found")
    return supervisor


# --------------------------------------------------------------------- runs


async def create_run(
    session: AsyncSession,
    order_id: str,
    supervisor_id: uuid.UUID,
    temporal_workflow_id: str,
    status: str,
    order_state: dict[str, Any],
    run_instructions: list[str],
) -> Run:
    existing = await session.scalar(select(Run).where(Run.order_id == order_id))
    if existing is not None:
        raise ConflictError(f"A run already exists for order '{order_id}'")

    run = Run(
        order_id=order_id,
        supervisor_id=supervisor_id,
        temporal_workflow_id=temporal_workflow_id,
        status=status,
        order_state=dict(order_state),
        memory_summary="",
        run_instructions=list(run_instructions),
        stats={},
    )
    session.add(run)
    await session.flush()
    await session.refresh(run)
    return run


async def list_runs(session: AsyncSession, status: str | None = None) -> list[Run]:
    query = select(Run).order_by(Run.created_at.desc())
    if status:
        query = query.where(Run.status == status)
    return list(await session.scalars(query))


async def get_run(session: AsyncSession, run_id: uuid.UUID) -> Run:
    run = await session.get(Run, run_id)
    if run is None:
        raise NotFoundError(f"Run {run_id} not found")
    return run


async def get_activities(
    session: AsyncSession, run_id: uuid.UUID, limit: int = 200
) -> list[ActivityRecord]:
    result = await session.scalars(
        select(ActivityRecord)
        .where(ActivityRecord.run_id == run_id)
        .order_by(ActivityRecord.seq.desc())
        .limit(limit)
    )
    return sorted(result, key=lambda record: record.seq)


async def save_run_snapshot(
    session: AsyncSession,
    run_id: uuid.UUID,
    status: str,
    order_state: dict[str, Any],
    memory_summary: str,
    run_instructions: list[str],
    latest_decision: dict[str, Any] | None,
    next_wake_at: datetime | None,
    last_wake_at: datetime | None,
    stats: dict[str, int],
    wake_guidance: list[str],
    final_output: dict[str, Any] | None,
    completed_at: datetime | None,
    activities: list[dict[str, Any]],
) -> None:
    """Write the current run state plus any new timeline entries.

    Activity inserts ignore conflicts on (run_id, seq), so the calling Activity
    can be retried without duplicating history.
    """
    run = await session.get(Run, run_id)
    if run is None:
        raise NotFoundError(f"Run {run_id} not found")

    run.status = status
    run.order_state = dict(order_state)
    run.memory_summary = memory_summary
    run.run_instructions = list(run_instructions)
    run.latest_decision = latest_decision
    run.next_wake_at = next_wake_at
    run.last_wake_at = last_wake_at
    run.stats = dict(stats)
    run.wake_guidance = list(wake_guidance)
    if final_output is not None:
        run.final_output = final_output
    if completed_at is not None:
        run.completed_at = completed_at

    if activities:
        await session.execute(
            pg_insert(ActivityRecord)
            .values(
                [
                    {
                        "id": uuid.uuid4(),
                        "run_id": run_id,
                        "seq": int(entry["seq"]),
                        "type": str(entry["type"]),
                        "source": str(entry.get("source", "workflow")),
                        "payload": entry.get("payload", {}),
                    }
                    for entry in activities
                ]
            )
            .on_conflict_do_nothing(constraint="uq_activities_run_id_seq")
        )
