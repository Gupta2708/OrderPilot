"""Shared FastAPI dependencies: database sessions and the Temporal client."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio.client import Client


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """One transaction per request; committed on success, rolled back on error."""
    factory: async_sessionmaker[AsyncSession] | None = getattr(
        request.app.state, "session_factory", None
    )
    if factory is None:  # pragma: no cover - only if startup did not run
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database is not configured"
        )
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_temporal_client(request: Request) -> Client:
    client: Client | None = getattr(request.app.state, "temporal_client", None)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Temporal is unavailable; run controls are offline",
        )
    return client


SessionDep = Annotated[AsyncSession, Depends(get_session)]
TemporalDep = Annotated[Client, Depends(get_temporal_client)]
