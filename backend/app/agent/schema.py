"""The structured output contract for the main agent.

Model output is validated with Pydantic before it can influence anything. The
workflow never sees this model directly: `normalize` converts a validated
decision into the plain dataclass the workflow consumes, so sleep handling and
the action allow-list are resolved inside the Activity.
"""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from app.domain.actions import ALL_ACTIONS
from app.domain.decision import DecisionKind, ProposedAction, SupervisorDecision
from app.domain.wake_policy import Severity

MIN_SLEEP_MINUTES = 1
MAX_SLEEP_MINUTES = 7 * 24 * 60
MAX_ACTIONS_PER_DECISION = 4
MAX_REASON_CHARS = 400
MAX_MEMORY_CHARS = 400


class SleepSpec(BaseModel):
    """How long the supervisor wants to sleep before its next review."""

    mode: Literal["duration", "timestamp"] = "duration"
    minutes: int | None = Field(default=None, ge=0, le=MAX_SLEEP_MINUTES)
    wake_at: str | None = None


class ProposedActionModel(BaseModel):
    tool: Literal[
        "message_fulfillment_team",
        "message_payments_team",
        "message_logistics_team",
        "message_customer",
        "create_internal_note",
    ]
    arguments: dict[str, Any] = Field(default_factory=dict)


class AgentDecisionModel(BaseModel):
    """Exactly what the LLM is allowed to return."""

    decision: Literal["ACT", "SLEEP", "NO_ACTION"]
    priority: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    reason_summary: str = Field(min_length=1, max_length=MAX_REASON_CHARS)
    actions: list[ProposedActionModel] = Field(default_factory=list)
    memory_update: str = Field(default="", max_length=MAX_MEMORY_CHARS)
    sleep: SleepSpec = Field(default_factory=SleepSpec)
    completion_recommended: bool = True


def _resolve_sleep_minutes(sleep: SleepSpec, default_wake_minutes: int, now: datetime) -> int:
    """Collapse the sleep spec to a bounded number of minutes.

    Resolved here, inside the Activity, so the workflow only ever sees an
    integer and never has to read a clock to interpret model output.
    """
    minutes = default_wake_minutes
    if sleep.mode == "timestamp" and sleep.wake_at:
        try:
            target = datetime.fromisoformat(sleep.wake_at.replace("Z", "+00:00"))
        except ValueError:
            target = None
        if target is not None:
            if target.tzinfo is None:
                target = target.replace(tzinfo=UTC)
            minutes = int((target - now).total_seconds() // 60)
    elif sleep.minutes is not None:
        minutes = sleep.minutes
    return max(MIN_SLEEP_MINUTES, min(minutes, MAX_SLEEP_MINUTES))


def normalize(
    model: AgentDecisionModel,
    allowed_actions: frozenset[str],
    default_wake_minutes: int,
    now: datetime,
) -> tuple[SupervisorDecision, list[str]]:
    """Validate a decision against the supervisor's configuration.

    Returns the workflow-facing decision plus the names of any tools that were
    rejected, so the rejection is auditable rather than silent.
    """
    kept: list[ProposedAction] = []
    rejected: list[str] = []
    for action in model.actions[:MAX_ACTIONS_PER_DECISION]:
        if action.tool in allowed_actions and action.tool in ALL_ACTIONS:
            kept.append(ProposedAction(tool=action.tool, arguments=dict(action.arguments)))
        else:
            rejected.append(action.tool)

    kind = DecisionKind(model.decision)
    if kind is DecisionKind.ACT and not kept:
        # Every proposed tool was disallowed, so this is no longer an ACT.
        kind = DecisionKind.NO_ACTION

    return (
        SupervisorDecision(
            decision=kind,
            priority=Severity(model.priority),
            reason_summary=model.reason_summary.strip(),
            actions=tuple(kept),
            memory_update=model.memory_update.strip(),
            sleep_minutes=_resolve_sleep_minutes(model.sleep, default_wake_minutes, now),
            completion_recommended=model.completion_recommended,
        ),
        rejected,
    )


def parse_decision(raw: str | dict[str, Any]) -> AgentDecisionModel:
    """Parse raw model output, raising ValidationError on anything malformed."""
    if isinstance(raw, str):
        return AgentDecisionModel.model_validate_json(raw)
    return AgentDecisionModel.model_validate(raw)


DECISION_JSON_SCHEMA_HINT = AgentDecisionModel.model_json_schema()

__all__ = [
    "AgentDecisionModel",
    "DECISION_JSON_SCHEMA_HINT",
    "MAX_ACTIONS_PER_DECISION",
    "ProposedActionModel",
    "SleepSpec",
    "ValidationError",
    "normalize",
    "parse_decision",
]
