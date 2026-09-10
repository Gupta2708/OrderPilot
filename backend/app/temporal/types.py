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
