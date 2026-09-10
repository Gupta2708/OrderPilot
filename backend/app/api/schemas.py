"""Request and response models for the control-plane API."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.actions import ALL_ACTIONS
from app.domain.wake_policy import WakeAggressiveness

MAX_INSTRUCTION_CHARS = 1000


class SupervisorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    base_instruction: str = Field(min_length=1, max_length=4000)
    allowed_actions: list[str] = Field(default_factory=lambda: list(ALL_ACTIONS))
    wake_aggressiveness: WakeAggressiveness = WakeAggressiveness.BALANCED
    default_wake_minutes: int = Field(default=60, ge=1, le=7 * 24 * 60)
    max_age_minutes: int = Field(default=7 * 24 * 60, ge=1)

    @field_validator("allowed_actions")
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


class TerminateRequest(BaseModel):
    reason: str = Field(default="Manually terminated", max_length=500)


class ControlResponse(BaseModel):
    run_id: uuid.UUID
    status: str


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
    next_wake_at: str | None = None
    last_wake_at: str | None = None
    pending_events: int = 0
    stats: dict[str, Any] = Field(default_factory=dict)
    final_output: dict[str, Any] | None = None
