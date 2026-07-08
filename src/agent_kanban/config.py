"""Application settings loaded from environment."""
from functools import lru_cache
from urllib.parse import urlparse

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# MCP streamable-HTTP transport enables DNS-rebinding protection by default and
# only allows localhost hosts/origins. When the board is deployed behind a
# public hostname (e.g. kanban.example.com) agents cannot reach /mcp until the
# hostname is whitelisted. These defaults keep localhost working in dev; prod
# sets MCP_ALLOWED_HOSTS / MCP_ALLOWED_ORIGINS (or just PUBLIC_URL — see below).
_DEFAULT_ALLOWED_HOSTS = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
_DEFAULT_ALLOWED_ORIGINS = [
    "http://127.0.0.1:*",
    "http://localhost:*",
    "http://[::1]:*",
]


def _derive_host_origin(url: str) -> tuple[list[str], list[str]] | None:
    """From a PUBLIC_URL like https://kanban.example.com derive (hosts, origins)
    allow-list entries suitable for the MCP transport. Returns None if the URL
    is localhost or unparseable — the defaults already cover localhost.

    The MCP SDK's host matcher accepts both an exact Host value and a
    ``host:*`` wildcard (matched as ``startswith(base + ":")``). A reverse
    proxy in front of the app typically forwards ``Host: kanban.example.com``
    with NO port (the standard https port is elided), so a lone
    ``kanban.example.com:*`` entry would NOT match. We therefore emit BOTH the
    bare hostname (exact match) and the ``:*`` wildcard (for explicit-port
    requests)."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = parsed.hostname
    if not host or host in {"127.0.0.1", "localhost", "::1"}:
        return None
    scheme = parsed.scheme or "https"
    port = f":{parsed.port}" if parsed.port else ""
    # Hosts: exact (proxy-style, no port) + wildcard (explicit-port clients).
    hosts = [host, f"{host}:*"]
    # Origins: scheme://host (no port) covers browsers; add explicit port if any.
    origins = [f"{scheme}://{host}", f"{scheme}://{host}{port}"]
    return hosts, origins


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://kanban:kanban@localhost:5436/kanban"
    port: int = 7331
    cors_origins: list[str] = ["http://localhost:5173"]
    session_secret: str = "dev-insecure-secret-change-me"  # override via env in prod
    public_url: str = "http://localhost:7331"
    bootstrap_admin_username: str = "admin"
    # MCP transport security — DNS-rebinding protection allow-lists.
    # PUBLIC_URL's hostname is auto-appended if it is non-localhost.
    mcp_allowed_hosts: list[str] = Field(default_factory=lambda: list(_DEFAULT_ALLOWED_HOSTS))
    mcp_allowed_origins: list[str] = Field(default_factory=lambda: list(_DEFAULT_ALLOWED_ORIGINS))
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

    def effective_mcp_allowed_hosts(self) -> list[str]:
        """MCP transport host allow-list: configured hosts + PUBLIC_URL hostname."""
        derived = _derive_host_origin(self.public_url)
        if not derived:
            return self.mcp_allowed_hosts
        return self.mcp_allowed_hosts + derived[0]

    def effective_mcp_allowed_origins(self) -> list[str]:
        """MCP transport origin allow-list: configured origins + PUBLIC_URL origin."""
        derived = _derive_host_origin(self.public_url)
        if not derived:
            return self.mcp_allowed_origins
        return self.mcp_allowed_origins + derived[1]


@lru_cache
def get_settings() -> Settings:
    return Settings()
