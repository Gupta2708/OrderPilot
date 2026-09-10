"""Temporal Activities: everything non-deterministic lives here.

LLM inference, action execution, memory compaction, and final-summary
generation all run as Activities so the workflow stays replay-safe.
"""

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine
from temporalio import activity

from app.agent.execution import ActionOutcome, compact_memory, execute_action
from app.agent.prompt import AgentContext
from app.agent.provider import build_provider, deterministic_fallback
from app.agent.schema import AgentDecisionModel, clean_guidance, normalize
from app.config import get_settings
from app.db import create_engine, create_session_factory
from app.domain.events import OrderEvent
from app.domain.wake_policy import Severity, WakeAggressiveness, evaluate_wake, meets_threshold
from app.repository import save_run_snapshot

logger = logging.getLogger(__name__)

# One engine per worker process, created on first use.
_ENGINE: AsyncEngine | None = None


def _persistence_engine() -> AsyncEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = create_engine()
    return _ENGINE


@dataclass
class DecisionRequest:
    order_id: str
    trigger: str
    base_instruction: str
    run_instructions: list[str] = field(default_factory=list)
    order_state: dict[str, Any] = field(default_factory=dict)
    memory_summary: str = ""
    triggering_event: dict[str, Any] | None = None
    wake_evaluation: dict[str, Any] | None = None
    recent_activity: list[dict[str, Any]] = field(default_factory=list)
    allowed_actions: list[str] = field(default_factory=list)
    default_wake_minutes: int = 60
    wake_guidance: list[str] = field(default_factory=list)


@dataclass
class DecisionResponse:
    """Workflow-facing decision: already validated and allow-list filtered."""

    decision: str
    priority: str
    reason_summary: str
    actions: list[dict[str, Any]]
    memory_update: str
    sleep_minutes: int
    completion_recommended: bool
    provider: str
    rejected_actions: list[str] = field(default_factory=list)
    fallback_used: bool = False
    wake_guidance: list[str] = field(default_factory=list)


@dataclass
class ActionRequest:
    order_id: str
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)
    allowed_actions: list[str] = field(default_factory=list)


@dataclass
class MemoryRequest:
    existing: str
    updates: list[str] = field(default_factory=list)


@dataclass
class FinalizeRequest:
    order_id: str
    status: str
    terminal_reason: str
    order_state: dict[str, Any] = field(default_factory=dict)
    memory_summary: str = ""
    executed_actions: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)


@dataclass
class FinalizeResponse:
    final_summary: str
    important_actions: list[dict[str, Any]]
    learnings: list[str]
    recommendations: list[str]


def _context_from(request: DecisionRequest) -> AgentContext:
    return AgentContext(
        order_id=request.order_id,
        trigger=request.trigger,
        base_instruction=request.base_instruction,
        run_instructions=list(request.run_instructions),
        order_state=dict(request.order_state),
        memory_summary=request.memory_summary,
        triggering_event=request.triggering_event,
        wake_evaluation=request.wake_evaluation,
        recent_activity=list(request.recent_activity),
        allowed_actions=list(request.allowed_actions),
        default_wake_minutes=request.default_wake_minutes,
        wake_guidance=list(request.wake_guidance),
    )


@activity.defn
async def make_decision(request: DecisionRequest) -> DecisionResponse:
    """Ask the agent what to do. Validates, retries once, then degrades safely."""
    settings = get_settings()
    context = _context_from(request)
    provider = build_provider(
        provider_name=settings.llm_provider,
        model=settings.anthropic_model,
        api_key=settings.anthropic_api_key,
    )

    model_output: AgentDecisionModel | None = None
    fallback_used = False
    for attempt in (1, 2):
        try:
            model_output = await provider.decide(context)
            break
        except (ValidationError, ValueError, RuntimeError) as error:
            # One safe retry, then a deterministic fallback rather than a
            # failed run or an unvalidated decision.
            logger.warning(
                "agent decision attempt %s failed (%s): %s", attempt, type(error).__name__, error
            )
        except Exception as error:  # noqa: BLE001 - provider/transport failures
            logger.warning("agent provider error on attempt %s (%s)", attempt, type(error).__name__)
    if model_output is None:
        model_output = deterministic_fallback(context)
        fallback_used = True

    decision, rejected = normalize(
        model_output,
        allowed_actions=frozenset(request.allowed_actions),
        default_wake_minutes=request.default_wake_minutes,
        now=datetime.now(UTC),
    )
    if rejected:
        logger.info("dropped disallowed tools for %s: %s", request.order_id, rejected)

    return DecisionResponse(
        decision=str(decision.decision),
        priority=str(decision.priority),
        reason_summary=decision.reason_summary,
        actions=[action.as_dict() for action in decision.actions],
        memory_update=decision.memory_update,
        sleep_minutes=decision.sleep_minutes,
        completion_recommended=decision.completion_recommended,
        provider="fallback" if fallback_used else provider.name,
        rejected_actions=rejected,
        fallback_used=fallback_used,
        wake_guidance=clean_guidance(model_output.wake_guidance),
    )


@dataclass
class ClassifyRequest:
    event: dict[str, Any] = field(default_factory=dict)
    order_state: dict[str, Any] = field(default_factory=dict)
    wake_guidance: list[str] = field(default_factory=list)
    aggressiveness: str = "BALANCED"


@dataclass
class ClassifyResponse:
    wake_now: bool
    severity: str
    category: str
    reason: str
    rule: str


@activity.defn
async def classify_event(request: ClassifyRequest) -> ClassifyResponse:
    """Level B: judge one ambiguous event.

    Only called when the deterministic table defers. Any failure falls back to
    the deterministic evaluation, so triage never depends on the model being up.
    """
    settings = get_settings()
    provider = build_provider(
        provider_name=settings.llm_provider,
        model=settings.anthropic_model,
        api_key=settings.anthropic_api_key,
    )
    event = OrderEvent(
        event_id=str(request.event.get("event_id", "")),
        type=str(request.event.get("type", "")),
        payload=dict(request.event.get("payload", {})),
    )
    try:
        aggressiveness = WakeAggressiveness(request.aggressiveness)
    except ValueError:
        aggressiveness = WakeAggressiveness.BALANCED

    try:
        result = await provider.classify(request.event, request.order_state, request.wake_guidance)
        severity = Severity(result.severity)
        # Sensitivity still governs: the classifier judges severity, the
        # supervisor's configuration decides whether that severity wakes it.
        wake_now = result.wake_now and meets_threshold(severity, aggressiveness)
        return ClassifyResponse(
            wake_now=wake_now,
            severity=str(severity),
            category=result.category,
            reason=result.reason,
            rule=f"ai_classifier:{provider.name}",
        )
    except Exception as error:  # noqa: BLE001 - any provider failure degrades safely
        logger.warning("classifier failed (%s); using deterministic rules", type(error).__name__)
        fallback = evaluate_wake(event, aggressiveness)
        return ClassifyResponse(
            wake_now=fallback.wake_now,
            severity=str(fallback.severity),
            category=fallback.category,
            reason=fallback.reason,
            rule="classifier_fallback_deterministic",
        )


@activity.defn
async def run_business_action(request: ActionRequest) -> dict[str, Any]:
    """Execute one simulated business action and return a structured result."""
    outcome: ActionOutcome = execute_action(
        tool=request.tool,
        arguments=dict(request.arguments),
        allowed_actions=frozenset(request.allowed_actions),
        order_id=request.order_id,
    )
    return outcome.as_dict()


@activity.defn
async def compact_run_memory(request: MemoryRequest) -> str:
    """Fold new notes into the compact rolling memory."""
    return compact_memory(request.existing, list(request.updates))


@activity.defn
async def finalize_run(request: FinalizeRequest) -> FinalizeResponse:
    """Produce the final summary, learnings, and recommendations."""
    executed = [action for action in request.executed_actions if action.get("ok")]
    customer_actions = [a for a in executed if a.get("tool") == "message_customer"]

    summary = (
        f"Order {request.order_id} finished as {request.status} ({request.terminal_reason}). "
        f"Handled {request.stats.get('events_received', 0)} events with "
        f"{request.stats.get('agent_wakeups', 0)} agent wake-ups and "
        f"{len(executed)} executed actions."
    )

    learnings: list[str] = []
    if request.order_state.get("payment", {}).get("status") == "failed":
        learnings.append("Payment failed at least once and needed payments-team attention.")
    if request.order_state.get("shipment", {}).get("status") == "delayed":
        learnings.append("Shipment was delayed; delivery risk appeared mid-run.")
    no_wake = request.stats.get("no_wake_events", 0)
    if no_wake:
        learnings.append(
            f"{no_wake} routine event{'s' if no_wake != 1 else ''} "
            f"{'were' if no_wake != 1 else 'was'} absorbed without waking the main agent."
        )
    if not learnings:
        learnings.append("Order progressed without notable incidents.")

    recommendations: list[str] = []
    if request.terminal_reason == "max_age_reached":
        recommendations.append(
            "Run hit its maximum age; review whether the age limit fits this order type."
        )
    if customer_actions:
        recommendations.append(
            f"{len(customer_actions)} customer message(s) were sent; review tone and timing."
        )
    if request.stats.get("fallback_decisions", 0):
        recommendations.append(
            "One or more decisions used the deterministic fallback; check provider health."
        )
    if not recommendations:
        recommendations.append("No process changes recommended for this run.")

    return FinalizeResponse(
        final_summary=summary,
        important_actions=executed,
        learnings=learnings,
        recommendations=recommendations,
    )


@dataclass
class SnapshotRequest:
    """One durable write of run progress: current state plus new timeline rows."""

    run_id: str
    status: str
    order_state: dict[str, Any] = field(default_factory=dict)
    memory_summary: str = ""
    run_instructions: list[str] = field(default_factory=list)
    latest_decision: dict[str, Any] | None = None
    next_wake_at: str | None = None
    last_wake_at: str | None = None
    stats: dict[str, int] = field(default_factory=dict)
    wake_guidance: list[str] = field(default_factory=list)
    final_output: dict[str, Any] | None = None
    completed_at: str | None = None
    activities: list[dict[str, Any]] = field(default_factory=list)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@activity.defn
async def persist_snapshot(request: SnapshotRequest) -> int:
    """Persist run state and new activities. Returns the rows offered for insert.

    Retry-safe: activity rows conflict on (run_id, seq) and are ignored, and the
    run row is a plain overwrite of the workflow's current truth.
    """
    engine = _persistence_engine()
    session_factory = create_session_factory(engine)
    async with session_factory() as session, session.begin():
        await save_run_snapshot(
            session,
            run_id=uuid.UUID(request.run_id),
            status=request.status,
            order_state=request.order_state,
            memory_summary=request.memory_summary,
            run_instructions=request.run_instructions,
            latest_decision=request.latest_decision,
            next_wake_at=_parse_iso(request.next_wake_at),
            last_wake_at=_parse_iso(request.last_wake_at),
            stats=request.stats,
            wake_guidance=request.wake_guidance,
            final_output=request.final_output,
            completed_at=_parse_iso(request.completed_at),
            activities=request.activities,
        )
    return len(request.activities)


ALL_ACTIVITIES: list[Callable[..., Any]] = [
    make_decision,
    classify_event,
    run_business_action,
    compact_run_memory,
    finalize_run,
    persist_snapshot,
]
