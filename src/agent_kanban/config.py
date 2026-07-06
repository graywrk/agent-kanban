"""Application settings loaded from environment."""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://kanban:kanban@localhost:5436/kanban"
    port: int = 7331
    cors_origins: list[str] = ["http://localhost:5173"]
    artifacts_dir: str = "~/.agent-kanban/artifacts"
    session_secret: str = "dev-insecure-secret-change-me"  # override via env in prod
    public_url: str = "http://localhost:7331"
    bootstrap_admin_username: str = "admin"
    # Read from BOOTSTRAP_ADMIN_PASSWORD (pydantic default) OR the explicit
    # AGENT_KANBAN_BOOTSTRAP_ADMIN_PASSWORD alias (preferred public name).
    bootstrap_admin_password: str = Field(
        default="",
        validation_alias="AGENT_KANBAN_BOOTSTRAP_ADMIN_PASSWORD",
    )

    # Known-insecure placeholder values shipped in the repo. The startup guard in
    # server._lifespan refuses to serve when one of these is in effect AND the
    # board is publicly deployed (PUBLIC_URL is https), since itsdangerous signs
    # the kanban_session cookie with this key — anyone reading the repo could
    # otherwise forge an admin session.
    _INSECURE_SECRETS = frozenset(
        {
            "",
            "dev-insecure-secret-change-me",
            "please-change-me-in-production",
        }
    )

    def is_insecure_session_secret(self) -> bool:
        """True if session_secret is a known public/empty placeholder.

        The startup path (server._lifespan) checks this to refuse serving on a
        public https deployment with a forgeable cookie key.
        """
        return self.session_secret in self._INSECURE_SECRETS


@lru_cache
def get_settings() -> Settings:
    return Settings()
