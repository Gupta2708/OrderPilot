"""Simulated execution of the five business actions, plus memory compaction.

Pure functions: the Activity wrappers in `app/temporal/activities.py` own the
Temporal concerns, these own the behaviour so they can be tested directly.
"""

from dataclasses import dataclass, field
from typing import Any

from app.domain.actions import ALL_ACTIONS, BusinessAction

MAX_MEMORY_LINES = 10
MAX_MEMORY_CHARS = 1200

# Argument each action needs; everything else is passed through untouched.
_REQUIRED_ARGUMENT: dict[str, str] = {
    BusinessAction.MESSAGE_FULFILLMENT_TEAM: "message",
    BusinessAction.MESSAGE_PAYMENTS_TEAM: "message",
    BusinessAction.MESSAGE_LOGISTICS_TEAM: "message",
    BusinessAction.MESSAGE_CUSTOMER: "message",
    BusinessAction.CREATE_INTERNAL_NOTE: "note",
}

_DEFAULT_TEXT: dict[str, str] = {
    BusinessAction.MESSAGE_FULFILLMENT_TEAM: "Please review this order's fulfillment status.",
    BusinessAction.MESSAGE_PAYMENTS_TEAM: "Please review this order's payment status.",
    BusinessAction.MESSAGE_LOGISTICS_TEAM: "Please review this order's delivery status.",
    BusinessAction.MESSAGE_CUSTOMER: "We are reviewing your order and will follow up shortly.",
    BusinessAction.CREATE_INTERNAL_NOTE: "Supervisor review recorded.",
}


@dataclass
class ActionOutcome:
    """Structured success/failure result for one executed action."""

    tool: str
    ok: bool
    detail: str
    arguments: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "ok": self.ok,
            "detail": self.detail,
            "arguments": self.arguments,
        }


def execute_action(
    tool: str, arguments: dict[str, Any], allowed_actions: frozenset[str], order_id: str
) -> ActionOutcome:
    """Validate and simulate one business action.

    The allow-list is re-checked here even though the Activity already filtered,
    so no execution path can reach a tool the supervisor does not permit.
    """
    if tool not in ALL_ACTIONS:
        return ActionOutcome(tool=tool, ok=False, detail=f"Unknown tool '{tool}'.")
    if tool not in allowed_actions:
        return ActionOutcome(
            tool=tool, ok=False, detail=f"Tool '{tool}' is not allowed for this supervisor."
        )

    key = _REQUIRED_ARGUMENT[tool]
    raw = arguments.get(key)
    text = str(raw).strip() if raw is not None else ""
    if not text:
        # A missing message is recoverable: substitute a safe default rather
        # than failing the whole decision.
        text = _DEFAULT_TEXT[tool]

    resolved = dict(arguments)
    resolved[key] = text
    recipient = "customer" if tool == BusinessAction.MESSAGE_CUSTOMER else "internal"
    return ActionOutcome(
        tool=tool,
        ok=True,
        detail=f"Simulated {tool} for order {order_id} ({recipient}): {text}",
        arguments=resolved,
    )


def compact_memory(existing: str, updates: list[str]) -> str:
    """Keep memory compact and factual.

    Deterministic on purpose: memory is replayed constantly, and a summarising
    LLM call here would add cost and non-determinism for little benefit at this
    size. Oldest lines are dropped first, and the whole thing is length-capped.
    """
    lines = [line.strip() for line in existing.splitlines() if line.strip()]
    for update in updates:
        cleaned = update.strip()
        if cleaned and (not lines or lines[-1] != cleaned):
            lines.append(cleaned)

    if len(lines) > MAX_MEMORY_LINES:
        dropped = len(lines) - MAX_MEMORY_LINES
        kept = lines[dropped:]
        kept.insert(0, f"[{dropped} earlier note(s) compacted]")
        lines = kept

    summary = "\n".join(lines)
    if len(summary) > MAX_MEMORY_CHARS:
        summary = summary[-MAX_MEMORY_CHARS:].lstrip()
    return summary
