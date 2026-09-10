"""API contract tests.

These exercise the real routers against a real database, with the Temporal
client faked, so HTTP behaviour and error mapping are covered without needing a
running Temporal service. `test_end_to_end.py` covers the real integration.
"""

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, get_temporal_client
from app.db import create_engine
from app.domain.actions import ALL_ACTIONS
from app.main import create_app
from app.services import runs as run_service

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION") != "1", reason="Set RUN_INTEGRATION=1 with migrated Postgres"
)


class FakeTemporalClient:
    """Records what the API asked Temporal to do."""

    def __init__(self, fail_signals: bool = False) -> None:
        self.started: list[Any] = []
        self.signals: list[tuple[str, tuple[Any, ...]]] = []
        self.fail_signals = fail_signals
        self.state: dict[str, Any] | None = None

    async def start_workflow(self, *args: Any, **kwargs: Any) -> Any:
        self.started.append(kwargs.get("id"))
        return object()

    def get_workflow_handle(self, workflow_id: str) -> Any:
        return _FakeHandle(self)


class _FakeHandle:
    def __init__(self, client: FakeTemporalClient) -> None:
        self._client = client

    async def signal(self, signal: Any, args: Any = None) -> None:
        """Mirrors the SDK: a signal takes an explicit args list."""
        if self._client.fail_signals:
            raise run_service.WorkflowUnavailableError("workflow is gone")
        name = getattr(signal, "__name__", str(signal))
        self._client.signals.append((name, tuple(args or ())))

    async def query(self, query: Any) -> dict[str, Any]:
        if self._client.state is None:
            raise RuntimeError("no live workflow")
        return self._client.state


async def _client(
    temporal: FakeTemporalClient,
) -> AsyncIterator[tuple[AsyncClient, FakeTemporalClient]]:
    """App wired to a real DB session and the fake Temporal client."""
    app = create_app()
    engine = create_engine()
    connection = await engine.connect()
    transaction = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False)

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_temporal_client] = lambda: temporal

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as http_client:
            yield http_client, temporal
    finally:
        await session.close()
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


async def _make_supervisor(http: AsyncClient, **overrides: Any) -> dict[str, Any]:
    payload = {
        "name": "Standard Order Supervisor",
        "base_instruction": "Supervise this order until it reaches a terminal state.",
        "allowed_actions": list(ALL_ACTIONS),
        "default_wake_minutes": 30,
    }
    payload.update(overrides)
    response = await http.post("/api/supervisors", json=payload)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


async def _make_run(http: AsyncClient, supervisor_id: str, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "order_id": f"ORD-{uuid.uuid4().hex[:8]}",
        "supervisor_id": supervisor_id,
        "order_context": {"customer_tier": "vip"},
        "initial_instructions": ["Watch this order closely."],
    }
    payload.update(overrides)
    response = await http.post("/api/runs", json=payload)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


# ------------------------------------------------------------ supervisors


def test_supervisor_can_be_created_listed_and_fetched() -> None:
    async def scenario() -> None:
        async for http, _temporal in _client(FakeTemporalClient()):
            created = await _make_supervisor(http)
            assert created["config"]["default_wake_minutes"] == 30
            assert created["config"]["wake_aggressiveness"] == "BALANCED"

            listed = await http.get("/api/supervisors")
            assert listed.status_code == 200
            assert any(item["id"] == created["id"] for item in listed.json())

            fetched = await http.get(f"/api/supervisors/{created['id']}")
            assert fetched.status_code == 200
            assert fetched.json()["name"] == created["name"]

    asyncio.run(scenario())


def test_unknown_supervisor_returns_404() -> None:
    async def scenario() -> None:
        async for http, _temporal in _client(FakeTemporalClient()):
            response = await http.get(f"/api/supervisors/{uuid.uuid4()}")
            assert response.status_code == 404

    asyncio.run(scenario())


def test_supervisor_rejects_unknown_actions() -> None:
    async def scenario() -> None:
        async for http, _temporal in _client(FakeTemporalClient()):
            response = await http.post(
                "/api/supervisors",
                json={
                    "name": "Bad",
                    "base_instruction": "x",
                    "allowed_actions": ["delete_database"],
                },
            )
            assert response.status_code == 422

    asyncio.run(scenario())


# -------------------------------------------------------------------- runs


def test_creating_a_run_starts_exactly_one_workflow() -> None:
    async def scenario() -> None:
        async for http, temporal in _client(FakeTemporalClient()):
            supervisor = await _make_supervisor(http)
            run = await _make_run(http, supervisor["id"])

            assert run["status"] == "PENDING"
            assert temporal.started == [f"order-supervisor:{run['order_id']}"]
            assert run["temporal_workflow_id"] == f"order-supervisor:{run['order_id']}"

    asyncio.run(scenario())


def test_duplicate_order_is_rejected() -> None:
    async def scenario() -> None:
        async for http, _temporal in _client(FakeTemporalClient()):
            supervisor = await _make_supervisor(http)
            run = await _make_run(http, supervisor["id"])

            duplicate = await http.post(
                "/api/runs", json={"order_id": run["order_id"], "supervisor_id": supervisor["id"]}
            )
            assert duplicate.status_code == 409

    asyncio.run(scenario())


def test_run_for_unknown_supervisor_returns_404() -> None:
    async def scenario() -> None:
        async for http, _temporal in _client(FakeTemporalClient()):
            response = await http.post(
                "/api/runs", json={"order_id": "ORD-x", "supervisor_id": str(uuid.uuid4())}
            )
            assert response.status_code == 404

    asyncio.run(scenario())


def test_events_instructions_and_controls_map_to_signals() -> None:
    async def scenario() -> None:
        async for http, temporal in _client(FakeTemporalClient()):
            supervisor = await _make_supervisor(http)
            run = await _make_run(http, supervisor["id"])
            run_id = run["id"]

            event = await http.post(
                f"/api/runs/{run_id}/events",
                json={"type": "payment_confirmed", "payload": {"amount": 42}},
            )
            assert event.status_code == 202
            assert event.json()["event_id"]

            assert (
                await http.post(
                    f"/api/runs/{run_id}/instructions", json={"instruction": "Escalate delays."}
                )
            ).status_code == 202
            assert (await http.post(f"/api/runs/{run_id}/pause")).status_code == 202
            assert (await http.post(f"/api/runs/{run_id}/resume")).status_code == 202
            assert (
                await http.post(f"/api/runs/{run_id}/terminate", json={"reason": "done"})
            ).status_code == 202

            sent = [name for name, _args in temporal.signals]
            assert sent == [
                "order_event",
                "add_instruction",
                "pause",
                "resume",
                "terminate",
            ]

    asyncio.run(scenario())


def test_supplied_event_id_is_preserved_for_deduplication() -> None:
    async def scenario() -> None:
        async for http, temporal in _client(FakeTemporalClient()):
            supervisor = await _make_supervisor(http)
            run = await _make_run(http, supervisor["id"])

            response = await http.post(
                f"/api/runs/{run['id']}/events",
                json={"type": "delivered", "event_id": "evt-fixed"},
            )
            assert response.json()["event_id"] == "evt-fixed"
            _name, args = temporal.signals[0]
            assert args[0]["event_id"] == "evt-fixed"

    asyncio.run(scenario())


def test_control_on_a_finished_workflow_returns_409() -> None:
    async def scenario() -> None:
        async for http, _temporal in _client(FakeTemporalClient(fail_signals=True)):
            supervisor = await _make_supervisor(http)
            run = await _make_run(http, supervisor["id"])

            response = await http.post(f"/api/runs/{run['id']}/pause")
            assert response.status_code == 409

    asyncio.run(scenario())


def test_operations_on_unknown_run_return_404() -> None:
    async def scenario() -> None:
        async for http, _temporal in _client(FakeTemporalClient()):
            missing = uuid.uuid4()
            assert (await http.get(f"/api/runs/{missing}")).status_code == 404
            assert (await http.get(f"/api/runs/{missing}/state")).status_code == 404
            assert (
                await http.post(f"/api/runs/{missing}/events", json={"type": "delivered"})
            ).status_code == 404

    asyncio.run(scenario())


def test_run_detail_exposes_timeline_memory_and_final_output_fields() -> None:
    async def scenario() -> None:
        async for http, _temporal in _client(FakeTemporalClient()):
            supervisor = await _make_supervisor(http)
            run = await _make_run(http, supervisor["id"])

            detail = await http.get(f"/api/runs/{run['id']}")
            assert detail.status_code == 200
            body = detail.json()
            assert body["timeline"] == []  # nothing persisted yet without a worker
            assert body["memory_summary"] == ""
            assert body["final_output"] is None
            assert body["run_instructions"] == ["Watch this order closely."]

    asyncio.run(scenario())


def test_state_prefers_the_workflow_and_falls_back_to_the_database() -> None:
    async def scenario() -> None:
        temporal = FakeTemporalClient()
        async for http, fake in _client(temporal):
            supervisor = await _make_supervisor(http)
            run = await _make_run(http, supervisor["id"])

            # No live workflow: the persisted snapshot answers.
            fallback = await http.get(f"/api/runs/{run['id']}/state")
            assert fallback.status_code == 200
            assert fallback.json()["source"] == "database"
            assert fallback.json()["status"] == "PENDING"

            # Live workflow present: it wins.
            fake.state = {
                "run_id": run["id"],
                "order_id": run["order_id"],
                "status": "SLEEPING",
                "paused": False,
                "terminal": False,
                "terminal_reason": None,
                "order_state": {"payment": {"status": "confirmed"}},
                "memory_summary": "Payment confirmed.",
                "run_instructions": [],
                "latest_decision": None,
                "latest_wake_decision": None,
                "executed_actions": [],
                "next_wake_at": None,
                "last_wake_at": None,
                "pending_events": 0,
                "stats": {"agent_wakeups": 1},
            }
            live = await http.get(f"/api/runs/{run['id']}/state")
            assert live.json()["source"] == "workflow"
            assert live.json()["status"] == "SLEEPING"
            assert live.json()["memory_summary"] == "Payment confirmed."

    asyncio.run(scenario())


def test_runs_can_be_listed_and_filtered_by_status() -> None:
    async def scenario() -> None:
        async for http, _temporal in _client(FakeTemporalClient()):
            supervisor = await _make_supervisor(http)
            run = await _make_run(http, supervisor["id"])

            listed = await http.get("/api/runs")
            assert listed.status_code == 200
            assert any(item["id"] == run["id"] for item in listed.json())

            filtered = await http.get("/api/runs", params={"status": "COMPLETED"})
            assert all(item["status"] == "COMPLETED" for item in filtered.json())

    asyncio.run(scenario())


# --------------------------------------------------------------- approvals


def test_supervisor_defaults_to_requiring_approval_for_customer_messages() -> None:
    async def scenario() -> None:
        async for http, _temporal in _client(FakeTemporalClient()):
            created = await _make_supervisor(http)
            assert created["config"]["require_approval_for"] == ["message_customer"]

    asyncio.run(scenario())


def test_approval_policy_rejects_unknown_actions() -> None:
    async def scenario() -> None:
        async for http, _temporal in _client(FakeTemporalClient()):
            response = await http.post(
                "/api/supervisors",
                json={
                    "name": "Bad policy",
                    "base_instruction": "x",
                    "require_approval_for": ["launch_missiles"],
                },
            )
            assert response.status_code == 422

    asyncio.run(scenario())


def test_approve_and_reject_map_to_signals() -> None:
    async def scenario() -> None:
        async for http, temporal in _client(FakeTemporalClient()):
            supervisor = await _make_supervisor(http)
            run = await _make_run(http, supervisor["id"])
            approval_id = str(uuid.uuid4())

            approved = await http.post(f"/api/runs/{run['id']}/approvals/{approval_id}/approve")
            assert approved.status_code == 202

            rejected = await http.post(
                f"/api/runs/{run['id']}/approvals/{approval_id}/reject",
                json={"reason": "Too early to contact the customer"},
            )
            assert rejected.status_code == 202

            sent = [name for name, _args in temporal.signals]
            assert sent == ["approve_action", "reject_action"]
            # The rejection carries both the approval id and the reason.
            assert temporal.signals[1][1] == (
                approval_id,
                "Too early to contact the customer",
            )

    asyncio.run(scenario())


def test_approval_on_a_finished_workflow_returns_409() -> None:
    async def scenario() -> None:
        async for http, _temporal in _client(FakeTemporalClient(fail_signals=True)):
            supervisor = await _make_supervisor(http)
            run = await _make_run(http, supervisor["id"])
            response = await http.post(f"/api/runs/{run['id']}/approvals/{uuid.uuid4()}/approve")
            assert response.status_code == 409

    asyncio.run(scenario())
