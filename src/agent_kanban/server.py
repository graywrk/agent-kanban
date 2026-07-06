"""FastAPI app factory."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_kanban.config import get_settings
from agent_kanban.routes import comments, progress, projects, tasks, ws


@asynccontextmanager
async def _lifespan(app: FastAPI):
    yield


def create_app() -> FastAPI:
    settings = get_settings()
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
    return app
