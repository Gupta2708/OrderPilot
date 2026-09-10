import asyncio

from temporalio.client import Client

from app.config import get_settings


async def connect_client() -> Client:
    settings = get_settings()
    return await asyncio.wait_for(
        Client.connect(settings.temporal_address, namespace=settings.temporal_namespace), timeout=10
    )
