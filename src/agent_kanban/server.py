"""FastAPI app factory."""
import contextlib
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from agent_kanban.config import get_settings
from agent_kanban.mcp_server import MCPAuthMiddleware, create_mcp
from agent_kanban.routes import artifacts, auth as auth_routes, comments, progress, projects, tasks, ws


async def _bootstrap_admin() -> None:
    """Create an admin from BOOTSTRAP_ADMIN_PASSWORD if set and no users exist.

    If the env var is unset, first-run uses POST /api/setup from the UI instead
    (the auto-generate-and-print path is removed so the operator sets the
    password in-app). Existing automation that sets
    ``AGENT_KANBAN_BOOTSTRAP_ADMIN_PASSWORD`` still works unchanged. Must run
    BEFORE the MCP session manager starts so the admin exists before any
    authenticated request can arrive.
    """
    from sqlmodel import select

    from agent_kanban.auth import hash_password
    from agent_kanban.db import AsyncSessionLocal
    from agent_kanban.models import User

    settings = get_settings()
    if not settings.bootstrap_admin_password:
        return  # UI /api/setup flow handles first-run
    async with AsyncSessionLocal() as session:
        existing = (await session.execute(select(User))).scalars().all()
        if existing:
            return
        session.add(
            User(
                username=settings.bootstrap_admin_username,
                password_hash=hash_password(settings.bootstrap_admin_password),
                is_admin=True,
            )
        )
        await session.commit()


def create_app() -> FastAPI:
    """Build a configured FastAPI app with the MCP server mounted at /mcp.

    Each call constructs its own FastMCP instance (via `create_mcp()`) so the
    MCP streamable-HTTP session manager — which is single-use per instance — is
    not shared across multiple app lifespans (e.g. when tests spin up several
    `TestClient`/app instances in one process).
    """
    settings = get_settings()
    mcp_instance = create_mcp()
    # Calling streamable_http_app() initializes the lazy session_manager that
    # the lifespan below runs for the app's lifetime.
    mcp_http_app = mcp_instance.streamable_http_app()

    @contextlib.asynccontextmanager
    async def _lifespan(app: FastAPI):
        # Refuse to serve with a known-insecure session secret when publicly
        # deployed (https). itsdangerous signs the kanban_session cookie with
        # settings.session_secret; a public placeholder lets anyone forge an
        # admin cookie. We only enforce on https because dev/test runs on http
        # and the dev default is intentionally insecure for local convenience.
        lifespan_settings = get_settings()
        if (
            lifespan_settings.is_insecure_session_secret()
            and lifespan_settings.public_url.startswith("https")
        ):
            raise RuntimeError(
                "SESSION_SECRET must be set to a strong random value when "
                "PUBLIC_URL is https. Generate one with: "
                'python -c "import secrets; print(secrets.token_urlsafe(32))"'
            )
        # Bootstrap the admin user BEFORE starting the MCP session manager so
        # the admin exists before any authenticated request can be served.
        await _bootstrap_admin()
        async with mcp_instance.session_manager.run():
            yield

    app = FastAPI(title="Agent Kanban", version="0.1.0", lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        session_cookie="kanban_session",
        same_site="lax",
        https_only=settings.public_url.startswith("https"),
    )
    app.include_router(projects.router)
    app.include_router(tasks.router)
    app.include_router(progress.router)
    app.include_router(comments.router)
    app.include_router(artifacts.router)
    app.include_router(auth_routes.router)
    app.include_router(ws.router)

    # Mount MCP HTTP transport at /mcp. With FastMCP's streamable_http_path="/",
    # the canonical endpoint is /mcp/ (and /mcp 307-redirects to it). The
    # MCPAuthMiddleware wraps the inner app so every /mcp request resolves a
    # Principal from the bearer header into a ContextVar that the tool
    # verifiers read.
    app.mount("/mcp", MCPAuthMiddleware(mcp_http_app))
    # Expose the FastMCP instance on the app so tests can drive its session
    # manager without re-deriving it from the mounted sub-app's routes.
    app.state.mcp = mcp_instance

    # Serve the built React frontend (if present) as a catch-all at "/".
    # Mounted LAST so it never shadows /api, /ws, or /mcp. In dev the Vite dev
    # server (web/) serves the SPA instead; in Docker the build is copied to
    # $AGENT_KANBAN_STATIC_DIR (default web/dist relative to CWD).
    static_dir = os.environ.get("AGENT_KANBAN_STATIC_DIR", "web/dist")
    if os.path.isdir(static_dir):
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app
