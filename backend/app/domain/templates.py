"""Ready-made supervisor templates.

Three deliberately different operating policies, so the difference between them
is visible in a demo rather than cosmetic: how eagerly they wake, which tools
they may use, and what needs a human.
"""

from dataclasses import dataclass, field
from typing import Any

from app.domain.actions import ALL_ACTIONS, BusinessAction
from app.domain.wake_policy import WakeAggressiveness


@dataclass(frozen=True)
class SupervisorTemplate:
    key: str
    name: str
    description: str
    base_instruction: str
    allowed_actions: list[str] = field(default_factory=lambda: list(ALL_ACTIONS))
    wake_aggressiveness: str = str(WakeAggressiveness.BALANCED)
    default_wake_minutes: int = 60
    max_age_minutes: int = 7 * 24 * 60
    require_approval_for: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "base_instruction": self.base_instruction,
            "allowed_actions": list(self.allowed_actions),
            "wake_aggressiveness": self.wake_aggressiveness,
            "default_wake_minutes": self.default_wake_minutes,
            "max_age_minutes": self.max_age_minutes,
            "require_approval_for": list(self.require_approval_for),
        }


TEMPLATES: tuple[SupervisorTemplate, ...] = (
    SupervisorTemplate(
        key="standard",
        name="Standard Order Supervisor",
        description="Balanced supervision for ordinary orders.",
        base_instruction=(
            "Supervise this order until it reaches a terminal state. Escalate real "
            "problems promptly, keep internal notes accurate, and avoid unnecessary "
            "customer contact."
        ),
        wake_aggressiveness=str(WakeAggressiveness.BALANCED),
        default_wake_minutes=60,
        require_approval_for=[str(BusinessAction.MESSAGE_CUSTOMER)],
    ),
    SupervisorTemplate(
        key="vip",
        name="VIP / High-Touch Supervisor",
        description="Wakes readily and communicates proactively for high-value orders.",
        base_instruction=(
            "Supervise this high-value order with close attention. Treat any delay or "
            "customer concern as urgent, escalate early, and keep the customer informed "
            "proactively rather than waiting to be asked."
        ),
        wake_aggressiveness=str(WakeAggressiveness.HIGH),
        default_wake_minutes=20,
        # Trusted to contact the customer directly; speed matters more here.
        require_approval_for=[],
    ),
    SupervisorTemplate(
        key="cost_conscious",
        name="Cost-Conscious Supervisor",
        description="Wakes only for critical problems and reviews infrequently.",
        base_instruction=(
            "Supervise this order with minimal intervention. Act only when something is "
            "genuinely wrong, prefer a single internal note over multiple messages, and "
            "do not contact the customer unless the problem affects them directly."
        ),
        allowed_actions=[
            str(BusinessAction.MESSAGE_FULFILLMENT_TEAM),
            str(BusinessAction.MESSAGE_PAYMENTS_TEAM),
            str(BusinessAction.MESSAGE_LOGISTICS_TEAM),
            str(BusinessAction.CREATE_INTERNAL_NOTE),
        ],
        wake_aggressiveness=str(WakeAggressiveness.LOW),
        default_wake_minutes=240,
        require_approval_for=[],
    ),
)

TEMPLATES_BY_KEY: dict[str, SupervisorTemplate] = {t.key: t for t in TEMPLATES}
