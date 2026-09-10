"""Run against migrated local Postgres with RUN_INTEGRATION=1; data is rolled back."""

import asyncio
import os
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import create_engine
from app.models import ActivityRecord, Run, Supervisor

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION") != "1", reason="Set RUN_INTEGRATION=1 with migrated Postgres"
)


def test_postgres_roundtrip_and_order_uniqueness() -> None:
    async def scenario() -> None:
        engine = create_engine()
        try:
            async with engine.connect() as connection:
                transaction = await connection.begin()
                try:
                    async with AsyncSession(bind=connection, expire_on_commit=False) as session:
                        supervisor = Supervisor(name="Foundation probe", base_instruction="Probe")
                        session.add(supervisor)
                        await session.flush()
                        order_id = f"probe-{uuid.uuid4()}"
                        run = Run(
                            order_id=order_id,
                            supervisor_id=supervisor.id,
                            temporal_workflow_id=order_id,
                            status="SCAFFOLD_TEST",
                            order_state={"probe": True},
                        )
                        session.add(run)
                        await session.flush()
                        session.add(
                            ActivityRecord(
                                run_id=run.id,
                                type="SCAFFOLD_TEST",
                                source="test",
                                payload={"ok": True},
                            )
                        )
                        await session.flush()
                        session.expire_all()
                        record = (
                            await session.scalars(select(Run).where(Run.order_id == order_id))
                        ).one()
                        assert record.order_state == {"probe": True}
                        assert record.created_at.tzinfo is not None
                        activity = (
                            await session.scalars(
                                select(ActivityRecord).where(ActivityRecord.run_id == record.id)
                            )
                        ).one()
                        assert activity.payload == {"ok": True}
                        supervisor_id = record.supervisor_id
                        with pytest.raises(IntegrityError):
                            async with session.begin_nested():
                                session.add(
                                    Run(
                                        order_id=order_id,
                                        supervisor_id=supervisor_id,
                                        temporal_workflow_id=f"different-{uuid.uuid4()}",
                                        status="SCAFFOLD_TEST",
                                    )
                                )
                                await session.flush()
                finally:
                    await transaction.rollback()
        finally:
            await engine.dispose()

    asyncio.run(scenario())
