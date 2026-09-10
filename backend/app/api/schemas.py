"""Request and response models for the control-plane API."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.actions import ALL_ACTIONS, BusinessAction
from app.domain.wake_policy import WakeAggressiveness

MAX_INSTRUCTION_CHARS = 1000


class SupervisorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    base_instruction: str = Field(min_length=1, max_length=4000)
    allowed_actions: list[str] = Field(default_factory=lambda: list(ALL_ACTIONS))
    wake_aggressiveness: WakeAggressiveness = WakeAggressiveness.BALANCED
    default_wake_minutes: int = Field(default=60, ge=1, le=7 * 24 * 60)
    max_age_minutes: int = Field(default=7 * 24 * 60, ge=1)
    # Sensitive tools a human must approve. Defaults to messaging the customer.
    require_approval_for: list[str] = Field(
        default_factory=lambda: [str(BusinessAction.MESSAGE_CUSTOMER)]
    )
    # 0 disables Continue-As-New; keep it low in development to exercise it.
    continue_as_new_after_events: int = Field(default=0, ge=0, le=10_000)

    @field_validator("allowed_actions", "require_approval_for")
    @classmethod
    def _known_actions_only(cls, value: list[str]) -> list[str]:
        unknown = [action for action in value if action not in ALL_ACTIONS]
        if unknown:
            raise ValueError(f"Unknown actions: {', '.join(unknown)}")
        return value


class SupervisorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    base_instruction: str
    allowed_actions: list[str]
    config: dict[str, Any]
    created_at: datetime


class RunCreate(BaseModel):
    order_id: str = Field(min_length=1, max_length=200)
    supervisor_id: uuid.UUID
    order_context: dict[str, Any] = Field(default_factory=dict)
    initial_instructions: list[str] = Field(default_factory=list)
    default_wake_minutes: int | None = Field(default=None, ge=1, le=7 * 24 * 60)
    max_age_minutes: int | None = Field(default=None, ge=1)


class RunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: str
    supervisor_id: uuid.UUID
    temporal_workflow_id: str
    status: str
    next_wake_at: datetime | None
    last_wake_at: datetime | None
    stats: dict[str, Any]
    created_at: datetime
    completed_at: datetime | None


class ActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    type: str
    source: str
    payload: dict[str, Any]
    created_at: datetime


class RunDetail(RunSummary):
    order_state: dict[str, Any]
    wake_guidance: list[str]
    memory_summary: str
    run_instructions: list[str]
    latest_decision: dict[str, Any] | None
    final_output: dict[str, Any] | None
    timeline: list[ActivityResponse]


class EventCreate(BaseModel):
    type: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)
    event_id: str | None = Field(default=None, max_length=200)


class EventAccepted(BaseModel):
    event_id: str
    accepted: bool = True


class InstructionCreate(BaseModel):
    instruction: str = Field(min_length=1, max_length=MAX_INSTRUCTION_CHARS)


class ApprovalDecision(BaseModel):
    reason: str = Field(default="Rejected by operator", max_length=500)


class TerminateRequest(BaseModel):
    reason: str = Field(default="Manually terminated", max_length=500)


class ControlResponse(BaseModel):
    run_id: uuid.UUID
    status: str


class SupervisorTemplateResponse(BaseModel):
    key: str
    name: str
    description: str
    base_instruction: str
    allowed_actions: list[str]
    wake_aggressiveness: str
    default_wake_minutes: int
    max_age_minutes: int
    require_approval_for: list[str]


class RunAnalytics(BaseModel):
    """Per-run counters, plus the derived numbers worth showing."""

    run_id: uuid.UUID
    order_id: str
    status: str
    events_received: int = 0
    agent_wakeups: int = 0
    no_wake_events: int = 0
    classifier_calls: int = 0
    scheduled_reviews: int = 0
    actions_executed: int = 0
    customer_actions: int = 0
    approvals_granted: int = 0
    approvals_denied: int = 0
    continuations: int = 0
    duration_seconds: int = 0
    wake_rate: float = 0.0
    actions_per_wake: float = 0.0


class RunStateResponse(BaseModel):
    """Live workflow state when available, otherwise the persisted snapshot."""

    run_id: uuid.UUID
    order_id: str
    source: str
    status: str
    paused: bool = False
    terminal: bool = False
    terminal_reason: str | None = None
    order_state: dict[str, Any] = Field(default_factory=dict)
    memory_summary: str = ""
    run_instructions: list[str] = Field(default_factory=list)
    latest_decision: dict[str, Any] | None = None
    latest_wake_decision: dict[str, Any] | None = None
    executed_actions: list[dict[str, Any]] = Field(default_factory=list)
    pending_approvals: list[dict[str, Any]] = Field(default_factory=list)
    next_wake_at: str | None = None
    last_wake_at: str | None = None
    pending_events: int = 0
    stats: dict[str, Any] = Field(default_factory=dict)
    wake_guidance: list[str] = Field(default_factory=list)
    final_output: dict[str, Any] | None = None
