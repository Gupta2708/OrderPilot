"""Workflow input/output contracts.

Plain dataclasses so both the Temporal client and replay-safe workflow code can
import them, and so the default JSON converter handles them without extra setup.
"""

from dataclasses import dataclass, field
from typing import Any

from app.domain.actions import ALL_ACTIONS
from app.domain.wake_policy import WakeAggressiveness

WORKFLOW_ID_PREFIX = "order-supervisor"

DEFAULT_WAKE_MINUTES = 60
DEFAULT_MAX_AGE_MINUTES = 7 * 24 * 60


def workflow_id_for_order(order_id: str) -> str:
    """Exactly one workflow per order; Temporal's ID uniqueness enforces it."""
    return f"{WORKFLOW_ID_PREFIX}:{order_id}"


@dataclass
class RunParams:
    run_id: str
    order_id: str
    supervisor_name: str = "Standard Order Supervisor"
    base_instruction: str = "Supervise this order until it reaches a terminal state."
    allowed_actions: list[str] = field(default_factory=lambda: list(ALL_ACTIONS))
    wake_aggressiveness: str = str(WakeAggressiveness.BALANCED)
    default_wake_minutes: int = DEFAULT_WAKE_MINUTES
    max_age_minutes: int = DEFAULT_MAX_AGE_MINUTES
    initial_instructions: list[str] = field(default_factory=list)
    order_context: dict[str, Any] = field(default_factory=dict)
    # Tools that a human must approve before they execute.
    require_approval_for: list[str] = field(default_factory=list)
    # Continue-As-New once this many events have been handled. 0 disables it.
    # Keep it low in development so the behaviour is easy to exercise.
    continue_as_new_after_events: int = 0
    # State carried across a Continue-As-New boundary; set by the workflow only.
    carried: "CarriedState | None" = None


@dataclass
class CarriedState:
    """The compact essentials that survive a Continue-As-New.

    Deliberately small: current state, not history. The full timeline already
    lives in PostgreSQL, so carrying it would defeat the purpose of resetting
    workflow history.
    """

    order_state: dict[str, Any] = field(default_factory=dict)
    memory_summary: str = ""
    instructions: list[str] = field(default_factory=list)
    wake_guidance: list[str] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)
    executed_actions: list[dict[str, Any]] = field(default_factory=list)
    pending_approvals: list[dict[str, Any]] = field(default_factory=list)
    pending_events: list[dict[str, Any]] = field(default_factory=list)
    recent_event_ids: list[str] = field(default_factory=list)
    latest_decision: dict[str, Any] | None = None
    started_at: str | None = None
    sequence: int = 0
    continuations: int = 0


@dataclass
class RunResult:
    run_id: str
    order_id: str
    status: str
    terminal_reason: str
    final_summary: str
    important_actions: list[dict[str, Any]]
    learnings: list[str]
    recommendations: list[str]
    stats: dict[str, int]
    order_state: dict[str, Any]
    memory_summary: str
