from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import get_settings


def create_engine() -> AsyncEngine:
    return create_async_engine(
        str(get_settings().database_url), pool_pre_ping=True, connect_args={"timeout": 5}
    )


async def check_database() -> None:
    engine = create_engine()
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    finally:
        await engine.dispose()
