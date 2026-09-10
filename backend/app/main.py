import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.api import runs, supervisors
from app.config import get_settings
from app.db import create_engine, create_session_factory
from app.temporal.client import connect_client

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["orderpilot-api"] = "orderpilot-api"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open the database engine and Temporal client once per process.

    A missing Temporal service does not stop the API from serving reads; the
    control endpoints report 503 until it is reachable.
    """
    engine = create_engine()
    app.state.db_engine = engine
    app.state.session_factory = create_session_factory(engine)
    try:
        app.state.temporal_client = await connect_client()
    except Exception as error:  # noqa: BLE001 - degraded start is intentional
        logger.warning("Temporal is unavailable at startup (%s)", type(error).__name__)
        app.state.temporal_client = None
    try:
        yield
    finally:
        await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="OrderPilot API", version="0.3.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    async def health() -> HealthResponse:
        """Process liveness only; infrastructure checks are separate CLI commands."""
        return HealthResponse()

    app.include_router(supervisors.router)
    app.include_router(runs.router)
    return app


app = create_app()
