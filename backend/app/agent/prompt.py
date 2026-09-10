"""Builds the compact agent context.

Only useful information goes into the prompt: the supervisor instruction, live
run instructions, structured order state, compact memory, the triggering event,
a small recent-activity window, and the allowed actions. The full history is
deliberately never included.
"""

import json
from dataclasses import dataclass, field
from typing import Any

RECENT_ACTIVITY_LIMIT = 8

SYSTEM_PROMPT = """You are an order operations supervisor for an e-commerce company.

You supervise ONE order. You are woken by the workflow that owns this order's
lifecycle: at start, when an important event arrives, or on a scheduled review.

Decide what to do now, and return only the structured decision.

Rules:
- Only propose tools from the allowed actions list. Anything else is discarded.
- Keep reason_summary to one or two auditable sentences. Do not include your
  internal reasoning; state the conclusion and the evidence for it.
- memory_update must be a short factual note that will still be useful later.
- Choose a sleep interval that matches urgency: minutes for an active incident,
  hours for a healthy order.
- You may set completion_recommended, but you do NOT control completion. The
  workflow decides when the run ends.
- Prefer NO_ACTION over inventing busywork."""


@dataclass
class AgentContext:
    """Everything the agent is allowed to see for one decision."""

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


def build_user_prompt(context: AgentContext) -> str:
    """Render the context as a compact, stable prompt."""
    sections: list[str] = [
        f"Order: {context.order_id}",
        f"Woken by: {context.trigger}",
        "",
        "Supervisor instruction:",
        context.base_instruction.strip() or "(none)",
    ]

    if context.run_instructions:
        sections += ["", "Live run instructions (most recent last):"]
        sections += [f"- {line}" for line in context.run_instructions]

    sections += [
        "",
        "Current order state:",
        json.dumps(context.order_state, indent=2, sort_keys=True),
    ]

    if context.memory_summary:
        sections += ["", "Memory so far:", context.memory_summary]

    if context.triggering_event is not None:
        sections += [
            "",
            "Triggering event:",
            json.dumps(context.triggering_event, indent=2, sort_keys=True),
        ]

    if context.wake_evaluation is not None:
        sections += [
            "",
            "Why the wake policy woke you:",
            json.dumps(context.wake_evaluation, indent=2, sort_keys=True),
        ]

    recent = context.recent_activity[-RECENT_ACTIVITY_LIMIT:]
    if recent:
        sections += ["", "Recent activity (most recent last):"]
        sections += [f"- {entry.get('type')}: {entry.get('summary', '')}" for entry in recent]

    sections += [
        "",
        "Allowed actions:",
        ", ".join(context.allowed_actions) or "(none)",
        "",
        f"Default review interval if nothing is urgent: {context.default_wake_minutes} minutes.",
    ]
    return "\n".join(sections)
