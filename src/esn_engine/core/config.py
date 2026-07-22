"""All the settings in one place, read from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://esn:esn@localhost:5433/esn"

    # Redis is optional. Without it the search just runs every time.
    redis_url: str | None = None
    cache_ttl_seconds: int = 300

    # The CLIP weights are about 600 MB, so I mount them instead of copying them in the image.
    models_dir: Path = Path("models")

    # The constant in the RRF formula, 1/(k + rank). 60 is the value from the paper.
    rrf_k: int = 60

    # How many rows each retriever returns before the ranks are fused.
    candidate_limit: int = 200
    result_limit: int = 40

    # Dropped whenever a query excludes anything. See docs/adr/0004, this used to be applied
    # on one endpoint and not on the other one.
    safety_floor_flags: tuple[str, ...] = ("reputational", "unusable")

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
