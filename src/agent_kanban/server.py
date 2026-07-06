"""FastAPI app factory."""
import contextlib
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from agent_kanban.config import get_settings
from agent_kanban.mcp_server import create_mcp
from agent_kanban.routes import artifacts, auth as auth_routes, comments, progress, projects, tasks, ws


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
    # the canonical endpoint is /mcp/ (and /mcp 307-redirects to it).
    app.mount("/mcp", mcp_http_app)

    # Serve the built React frontend (if present) as a catch-all at "/".
    # Mounted LAST so it never shadows /api, /ws, or /mcp. In dev the Vite dev
    # server (web/) serves the SPA instead; in Docker the build is copied to
    # $AGENT_KANBAN_STATIC_DIR (default web/dist relative to CWD).
    static_dir = os.environ.get("AGENT_KANBAN_STATIC_DIR", "web/dist")
    if os.path.isdir(static_dir):
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app
