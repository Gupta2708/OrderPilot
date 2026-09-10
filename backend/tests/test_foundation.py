import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.checks import check
from app.config import Settings
from app.main import create_app


def test_liveness_without_infrastructure() -> None:
    async def scenario() -> None:
        async with AsyncClient(
            transport=ASGITransport(app=create_app()), base_url="http://test"
        ) as client:
            response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "service": "orderpilot-api"}

    asyncio.run(scenario())


def test_invalid_database_config_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(database_url="not-a-url")


def test_checks_report_failure_without_leaking_credentials(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with patch("app.checks.check_database", AsyncMock(side_effect=RuntimeError("secret-password"))):
        assert asyncio.run(check("database")) is False
    output = capsys.readouterr().out
    assert "FAIL" in output
    assert "secret-password" not in output


def test_checks_report_success() -> None:
    with patch("app.checks.check_database", AsyncMock(return_value=None)):
        assert asyncio.run(check("database")) is True
