from functools import lru_cache
from pathlib import Path

from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    database_url: PostgresDsn = PostgresDsn(
        "postgresql+asyncpg://orderpilot:orderpilot_dev@127.0.0.1:5432/orderpilot"
    )
    temporal_address: str = Field(default="127.0.0.1:7233", min_length=1)
    temporal_namespace: str = Field(default="default", min_length=1)
    temporal_task_queue: str = Field(default="orderpilot", min_length=1)
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
