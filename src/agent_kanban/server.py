"""FastAPI app factory."""
import contextlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_kanban.config import get_settings
from agent_kanban.mcp_server import create_mcp
from agent_kanban.routes import comments, progress, projects, tasks, ws


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
    app.include_router(projects.router)
    app.include_router(tasks.router)
    app.include_router(progress.router)
    app.include_router(comments.router)
    app.include_router(ws.router)

    # Mount MCP HTTP transport at /mcp. With FastMCP's streamable_http_path="/",
    # the canonical endpoint is /mcp/ (and /mcp 307-redirects to it).
    app.mount("/mcp", mcp_http_app)

    return app
