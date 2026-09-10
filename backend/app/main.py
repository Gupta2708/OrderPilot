from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import get_settings


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["orderpilot-api"] = "orderpilot-api"


def create_app() -> FastAPI:
    app = FastAPI(title="OrderPilot API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["GET"],
        allow_headers=["Content-Type"],
    )

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    async def health() -> HealthResponse:
        """Process liveness only; infrastructure checks are separate CLI commands."""
        return HealthResponse()

    return app


app = create_app()
