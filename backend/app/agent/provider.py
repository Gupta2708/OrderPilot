"""LLM provider abstraction: one real provider plus a deterministic mock.

The mock is not a stub for tests only. It is a supported runtime mode so the
whole product can be demonstrated without an API key, and it reuses the same
deterministic policy the workflow was proven against in Stage 1.
"""

from typing import Protocol

from app.agent.prompt import SYSTEM_PROMPT, AgentContext, build_user_prompt
from app.agent.schema import AgentDecisionModel, ProposedActionModel, SleepSpec
from app.domain.decision import Trigger, decide
from app.domain.events import OrderEvent
from app.domain.wake_policy import Severity, WakeEvaluation, evaluate_wake

MAX_DECISION_TOKENS = 4096


class LLMProvider(Protocol):
    """One decision in, one validated decision out."""

    name: str

    async def decide(self, context: AgentContext) -> AgentDecisionModel: ...


class MockProvider:
    """Deterministic provider. Same behaviour every run, no network, no key."""

    name = "mock"

    async def decide(self, context: AgentContext) -> AgentDecisionModel:
        event: OrderEvent | None = None
        evaluation: WakeEvaluation | None = None
        if context.triggering_event is not None:
            event = OrderEvent(
                event_id=str(context.triggering_event.get("event_id", "")),
                type=str(context.triggering_event.get("type", "")),
                payload=dict(context.triggering_event.get("payload", {})),
            )
            evaluation = evaluate_wake(event)

        try:
            trigger = Trigger(context.trigger)
        except ValueError:
            trigger = Trigger.SCHEDULED_TIMER

        decision = decide(
            trigger=trigger,
            event=event,
            wake_evaluation=evaluation,
            order_state=context.order_state,
            instructions=tuple(context.run_instructions),
            allowed_actions=frozenset(context.allowed_actions),
            default_wake_minutes=context.default_wake_minutes,
        )
        return AgentDecisionModel(
            decision=str(decision.decision),  # type: ignore[arg-type]
            priority=str(decision.priority),  # type: ignore[arg-type]
            reason_summary=decision.reason_summary,
            actions=[
                ProposedActionModel(tool=action.tool, arguments=action.arguments)  # type: ignore[arg-type]
                for action in decision.actions
            ],
            memory_update=decision.memory_update,
            sleep=SleepSpec(mode="duration", minutes=decision.sleep_minutes),
            completion_recommended=decision.completion_recommended,
        )


class ClaudeProvider:
    """Real provider, backed by the Anthropic Python SDK.

    Uses structured outputs so the response is schema-valid on arrival, and
    server-side refusal fallbacks so a declined request is routed rather than
    surfacing as an unusable response.
    """

    name = "claude"

    def __init__(self, model: str, api_key: str | None = None, timeout_seconds: float = 60.0):
        # Imported lazily so the mock path never requires the SDK to be usable.
        from anthropic import AsyncAnthropic

        self._model = model
        # api_key=None lets the SDK resolve credentials from the environment.
        self._client = AsyncAnthropic(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=2,
        )

    async def decide(self, context: AgentContext) -> AgentDecisionModel:
        response = await self._client.beta.messages.parse(
            model=self._model,
            max_tokens=MAX_DECISION_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_user_prompt(context)}],
            output_format=AgentDecisionModel,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("Model declined to produce a decision for this order context")
        parsed = response.parsed_output
        if parsed is None:
            raise ValueError("Model returned no parsable structured decision")
        return parsed


def build_provider(
    provider_name: str, model: str, api_key: str | None, timeout_seconds: float = 60.0
) -> LLMProvider:
    """Select the configured provider, falling back to the mock when unusable."""
    if provider_name == "claude":
        return ClaudeProvider(model=model, api_key=api_key, timeout_seconds=timeout_seconds)
    return MockProvider()


def deterministic_fallback(context: AgentContext) -> AgentDecisionModel:
    """Last-resort decision used when the real provider cannot be trusted.

    Never acts. It records the failure and schedules an ordinary review, so a
    provider outage degrades to a quiet supervisor instead of a wrong one.
    """
    return AgentDecisionModel(
        decision="NO_ACTION",
        priority=str(Severity.LOW),  # type: ignore[arg-type]
        reason_summary=(
            "Agent output was unavailable or failed validation; taking no action "
            "and scheduling the next scheduled review."
        ),
        actions=[],
        memory_update="Agent decision unavailable; no action taken.",
        sleep=SleepSpec(mode="duration", minutes=context.default_wake_minutes),
        completion_recommended=False,
    )
