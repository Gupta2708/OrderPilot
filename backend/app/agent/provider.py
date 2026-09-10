"""LLM provider abstraction: one real provider plus a deterministic mock.

The mock is not a stub for tests only. It is a supported runtime mode so the
whole product can be demonstrated without an API key, and it reuses the same
deterministic policy the workflow was proven against in Stage 1.
"""

import json
from typing import Any, Protocol

from pydantic import BaseModel

from app.agent.prompt import (
    CLASSIFIER_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    AgentContext,
    build_classifier_prompt,
    build_user_prompt,
)
from app.agent.schema import (
    AgentDecisionModel,
    ProposedActionModel,
    SleepSpec,
    WakeClassification,
)
from app.config import get_settings
from app.domain.decision import Trigger, decide
from app.domain.events import OrderEvent
from app.domain.wake_policy import Severity, WakeEvaluation, evaluate_wake

MAX_DECISION_TOKENS = 4096
MAX_CLASSIFIER_TOKENS = 512


class LLMProvider(Protocol):
    """One decision in, one validated decision out."""

    name: str

    async def decide(self, context: AgentContext) -> AgentDecisionModel: ...

    async def classify(
        self, event: dict[str, Any], order_state: dict[str, Any], guidance: list[str]
    ) -> WakeClassification: ...


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

    async def classify(
        self, event: dict[str, Any], order_state: dict[str, Any], guidance: list[str]
    ) -> WakeClassification:
        evaluation = evaluate_wake(
            OrderEvent(
                event_id=str(event.get("event_id", "")),
                type=str(event.get("type", "")),
                payload=dict(event.get("payload", {})),
            )
        )
        return WakeClassification(
            wake_now=evaluation.wake_now,
            severity=str(evaluation.severity),  # type: ignore[arg-type]
            category=evaluation.category,
            reason=evaluation.reason,
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

    async def classify(
        self, event: dict[str, Any], order_state: dict[str, Any], guidance: list[str]
    ) -> WakeClassification:
        """A small, cheap call: this runs on every ambiguous event."""
        response = await self._client.beta.messages.parse(
            model=self._model,
            max_tokens=MAX_CLASSIFIER_TOKENS,
            system=CLASSIFIER_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": build_classifier_prompt(event, order_state, guidance),
                }
            ],
            output_format=WakeClassification,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("Model declined to classify this event")
        parsed = response.parsed_output
        if parsed is None:
            raise ValueError("Model returned no parsable classification")
        return parsed


class OpenRouterProvider:
    """Real provider via OpenRouter, which exposes an OpenAI-compatible API.

    Used when the available credential is an OpenRouter key rather than an
    Anthropic one. Structured output is requested with a JSON schema; if the
    chosen model does not honour it, the response is still validated with
    Pydantic and a malformed reply is handled by the caller's retry and
    deterministic fallback.
    """

    name = "openrouter"

    def __init__(
        self,
        model: str,
        api_key: str | None,
        base_url: str,
        timeout_seconds: float = 60.0,
    ):
        # Imported lazily so the mock path never requires the SDK to be usable.
        from openai import AsyncOpenAI

        self._model = model
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=2,
            # OpenRouter uses these for attribution; both are optional.
            default_headers={"X-Title": "OrderPilot"},
        )

    async def _complete(
        self, system: str, user: str, schema_model: type[BaseModel], max_tokens: int
    ) -> dict[str, Any]:
        response = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema_model.__name__,
                    # Not strict: the action arguments allow extra keys, which
                    # strict mode forbids. Output is validated with Pydantic
                    # either way, and malformed replies hit the retry path.
                    "strict": False,
                    "schema": schema_model.model_json_schema(),
                },
            },
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Provider returned an empty response")
        return _extract_json(content)

    async def decide(self, context: AgentContext) -> AgentDecisionModel:
        payload = await self._complete(
            SYSTEM_PROMPT, build_user_prompt(context), AgentDecisionModel, MAX_DECISION_TOKENS
        )
        return AgentDecisionModel.model_validate(payload)

    async def classify(
        self, event: dict[str, Any], order_state: dict[str, Any], guidance: list[str]
    ) -> WakeClassification:
        payload = await self._complete(
            CLASSIFIER_SYSTEM_PROMPT,
            build_classifier_prompt(event, order_state, guidance),
            WakeClassification,
            MAX_CLASSIFIER_TOKENS,
        )
        return WakeClassification.model_validate(payload)


def _extract_json(content: str) -> dict[str, Any]:
    """Parse a JSON object from a model reply.

    Some models wrap JSON in prose or a code fence even when asked not to, so
    fall back to the outermost braces before giving up.
    """
    text = content.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text.removeprefix("json").strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("Provider response contained no JSON object") from None
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Provider response was not a JSON object")
    return parsed


def build_provider(
    provider_name: str, model: str, api_key: str | None, timeout_seconds: float = 60.0
) -> LLMProvider:
    """Select the configured provider, falling back to the mock when unusable."""
    if provider_name == "claude":
        return ClaudeProvider(model=model, api_key=api_key, timeout_seconds=timeout_seconds)
    if provider_name == "openrouter":
        settings = get_settings()
        return OpenRouterProvider(
            model=settings.openrouter_model,
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            timeout_seconds=timeout_seconds,
        )
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
