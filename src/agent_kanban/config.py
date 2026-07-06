"""Application settings loaded from environment."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://kanban:kanban@localhost:5436/kanban"
    port: int = 7331
    cors_origins: list[str] = ["http://localhost:5173"]
    artifacts_dir: str = "~/.agent-kanban/artifacts"


@lru_cache
def get_settings() -> Settings:
    return Settings()
