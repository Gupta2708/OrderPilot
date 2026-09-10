"""Test isolation.

The test suite must never depend on whichever provider a developer has
configured in `.env`, and must never make a paid API call. Environment
variables take priority over the dotenv file in pydantic-settings, so forcing
the mock provider here overrides any local configuration.
"""

import os

os.environ["LLM_PROVIDER"] = "mock"
os.environ.pop("OPENROUTER_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

assert get_settings().llm_provider == "mock", "tests must run against the mock provider"
