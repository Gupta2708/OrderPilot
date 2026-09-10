"""Stage 3 exit gate: the full P0 backend exercised over HTTP.

Real database, real worker, real workflow, Temporal's time-skipping test server.
Unlike the other suites this one commits, so it cleans up the rows it creates.
"""

import asyncio
import os
import uuid
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app.db import create_engine, create_session_factory
from app.main import create_app
from app.models import ActivityRecord, Run, Supervisor
from app.temporal.activities import ALL_ACTIVITIES
from app.temporal.workflow import ActivityType, OrderSupervisorWorkflow

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION") != "1", reason="Set RUN_INTEGRATION=1 with migrated Postgres"
)

TASK_QUEUE = "orderpilot"  # must match settings so the API starts work the worker sees


async def _wait_for(http: AsyncClient, run_id: str, predicate: Any, attempts: int = 100) -> Any:
    body: Any = None
    for _ in range(attempts):
        response = await http.get(f"/api/runs/{run_id}")
        body = response.json()
        if predicate(body):
            return body
        await asyncio.sleep(0.1)
    raise AssertionError(f"condition never became true; last body: {body}")


async def _cleanup(session_factory: Any, run_id: uuid.UUID, supervisor_id: uuid.UUID) -> None:
    async with session_factory() as session, session.begin():
        await session.execute(delete(ActivityRecord).where(ActivityRecord.run_id == run_id))
        await session.execute(delete(Run).where(Run.id == run_id))
        await session.execute(delete(Supervisor).where(Supervisor.id == supervisor_id))


def test_full_p0_backend_flow_without_a_frontend() -> None:
    async def scenario() -> None:
        engine = create_engine()
        session_factory = create_session_factory(engine)
        env = await WorkflowEnvironment.start_time_skipping()
        run_id: uuid.UUID | None = None
        supervisor_id: uuid.UUID | None = None
        try:
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[OrderSupervisorWorkflow],
                activities=ALL_ACTIVITIES,
            ):
                app = create_app()
                app.state.db_engine = engine
                app.state.session_factory = session_factory
                app.state.temporal_client = env.client

                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as http:
                    # 1. Configure a supervisor.
                    supervisor = await http.post(
                        "/api/supervisors",
                        json={
                            "name": "E2E Supervisor",
                            "base_instruction": "Supervise this order.",
                            "default_wake_minutes": 30,
                        },
                    )
                    assert supervisor.status_code == 201, supervisor.text
                    supervisor_id = uuid.UUID(supervisor.json()["id"])

                    # 2. Start a run; this starts the workflow.
                    order_id = f"ORD-E2E-{uuid.uuid4().hex[:8]}"
                    created = await http.post(
                        "/api/runs",
                        json={
                            "order_id": order_id,
                            "supervisor_id": str(supervisor_id),
                            "order_context": {"customer_tier": "vip"},
                        },
                    )
                    assert created.status_code == 201, created.text
                    run_id = uuid.UUID(created.json()["id"])

                    # 3. The start wake is persisted to Postgres by the workflow.
                    body = await _wait_for(
                        http, str(run_id), lambda b: b["status"] == "SLEEPING" and b["timeline"]
                    )
                    types = [entry["type"] for entry in body["timeline"]]
                    assert ActivityType.RUN_STARTED in types
                    assert ActivityType.AGENT_DECISION in types
                    assert body["stats"]["agent_wakeups"] == 1

                    # 4. Live state comes from the workflow itself.
                    state = await http.get(f"/api/runs/{run_id}/state")
                    assert state.json()["source"] == "workflow"

                    # 5. A routine event updates state without waking the agent.
                    assert (
                        await http.post(
                            f"/api/runs/{run_id}/events", json={"type": "payment_confirmed"}
                        )
                    ).status_code == 202
                    body = await _wait_for(
                        http, str(run_id), lambda b: b["stats"].get("events_received") == 1
                    )
                    assert body["stats"]["no_wake_events"] == 1
                    assert body["stats"]["agent_wakeups"] == 1
                    assert body["order_state"]["payment"]["status"] == "confirmed"

                    # 6. A live instruction plus an important event drives an action.
                    assert (
                        await http.post(
                            f"/api/runs/{run_id}/instructions",
                            json={"instruction": "If shipment is delayed, escalate immediately."},
                        )
                    ).status_code == 202
                    assert (
                        await http.post(
                            f"/api/runs/{run_id}/events",
                            json={"type": "shipment_delayed", "payload": {"reason": "storm"}},
                        )
                    ).status_code == 202
                    body = await _wait_for(
                        http, str(run_id), lambda b: b["stats"].get("actions_executed", 0) >= 1
                    )
                    executed = [
                        entry
                        for entry in body["timeline"]
                        if entry["type"] == ActivityType.ACTION_EXECUTED
                    ]
                    assert any(
                        entry["payload"]["tool"] == "message_logistics_team" for entry in executed
                    )
                    assert body["memory_summary"]
                    assert body["latest_decision"]["trigger"] == "SIGNAL"

                    # 7. A duplicate event is ignored.
                    for _ in range(2):
                        await http.post(
                            f"/api/runs/{run_id}/events",
                            json={"type": "customer_message_received", "event_id": "dupe-1"},
                        )
                    body = await _wait_for(
                        http,
                        str(run_id),
                        lambda b: any(
                            e["type"] == ActivityType.EVENT_DUPLICATE_IGNORED for e in b["timeline"]
                        ),
                    )

                    # 8. Pause and resume are honoured.
                    assert (await http.post(f"/api/runs/{run_id}/pause")).status_code == 202
                    await _wait_for(http, str(run_id), lambda b: b["status"] == "PAUSED")
                    assert (await http.post(f"/api/runs/{run_id}/resume")).status_code == 202

                    # 9. A terminal event completes the run and persists the final output.
                    assert (
                        await http.post(f"/api/runs/{run_id}/events", json={"type": "delivered"})
                    ).status_code == 202
                    body = await _wait_for(
                        http, str(run_id), lambda b: b["final_output"] is not None
                    )
                    assert body["status"] == "COMPLETED"
                    assert body["completed_at"] is not None
                    final = body["final_output"]
                    assert final["terminal_reason"] == "delivered"
                    assert final["final_summary"]
                    assert final["learnings"]
                    assert final["recommendations"]

                    # 10. The timeline is ordered, complete, and free of duplicates.
                    seqs = [entry["seq"] for entry in body["timeline"]]
                    assert seqs == sorted(seqs)
                    assert len(seqs) == len(set(seqs))
                    assert ActivityType.FINAL_OUTPUT in [e["type"] for e in body["timeline"]]

                    # 11. A completed run still answers, now from the database.
                    state = await http.get(f"/api/runs/{run_id}/state")
                    assert state.status_code == 200
                    assert state.json()["status"] == "COMPLETED"
        finally:
            if run_id is not None and supervisor_id is not None:
                await _cleanup(session_factory, run_id, supervisor_id)
            await env.shutdown()
            await engine.dispose()

    asyncio.run(scenario())
