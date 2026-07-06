"""Shared pytest fixtures.

Each test run uses a fresh throwaway Postgres database. We connect to the
default `postgres` maintenance DB, create a unique `kanban_test_<pid>_<ts>`
database, run alembic upgrades against it, and drop it on teardown.
"""
import asyncio
import os
import time
import uuid

import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DB_TEMPLATE = "postgresql://kanban:kanban@localhost:5436/postgres"


async def _create_test_db() -> str:
    unique = f"kanban_test_{os.getpid()}_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    conn = await asyncpg.connect(TEST_DB_TEMPLATE)
    try:
        await conn.execute(f'CREATE DATABASE "{unique}"')
    finally:
        await conn.close()
    return unique


async def _drop_test_db(name: str) -> None:
    conn = await asyncpg.connect(TEST_DB_TEMPLATE)
    try:
        await conn.execute(
            f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'
        )
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_db_name():
    name = await _create_test_db()
    yield name
    await _drop_test_db(name)


@pytest_asyncio.fixture
async def db_url(test_db_name, monkeypatch):
    url = f"postgresql+asyncpg://kanban:kanban@localhost:5436/{test_db_name}"
    monkeypatch.setenv("DATABASE_URL", url)
    # Apply migrations to the fresh DB.
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url.replace("+asyncpg", ""))
    command.upgrade(cfg, "head")
    yield url


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engines():
    """Dispose any cached `agent_kanban.db` engines between tests.

    pytest-asyncio (auto mode) runs each test on a fresh event loop; asyncpg
    connections bind to the loop active when first checked out. Each test's
    throwaway DB gets its own engine (keyed on its unique DATABASE_URL), and we
    dispose every cached engine afterward so connections never outlive their loop.
    """
    yield
    from agent_kanban import db as _db

    while _db._engines:
        _, engine = _db._engines.popitem()
        await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables(db_url):
    """Truncate all tables before each test.

    Every test shares one session-scoped throwaway DB (see `test_db_name`), so
    without truncation rows leak between tests and ordering-sensitive queries
    (e.g. list_tasks, get_next_task over READY rows) become non-deterministic.
    autouse so REST/WS route tests that never touch the `session` fixture still
    start from a clean slate.
    """
    engine = create_async_engine(db_url)
    try:
        async with engine.begin() as conn:
            from sqlalchemy import text

            await conn.execute(
                text(
                    "TRUNCATE TABLE project, task, progressevent, comment, artifact, "
                    '"user", token '
                    "RESTART IDENTITY CASCADE"
                )
            )
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def session(db_url):
    engine = create_async_engine(db_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest.fixture(autouse=True)
def _stub_mcp_principal(monkeypatch):
    """Stub the MCP principal verifiers for in-process tool calls.

    `mcp.call_tool` runs tools directly — there is no HTTP request, so the
    ``_mcp_principal`` ContextVar (populated by MCPAuthMiddleware during real
    serving) is empty and the verifiers would reject every call. We patch the
    two verifier functions on the mcp_server module so they return a fixed
    Principal(agent_name="codex") without touching the request path. Tests that
    pass ``agent="codex"`` pass; tests asserting authz-rejection (agent !=
    codex) still fail as intended. The e2e test overrides this to "hermes" via
    its own monkeypatch (last write wins on the shared function-scoped
    monkeypatch). Harmless for REST-only tests that never invoke MCP tools.
    """
    from agent_kanban import mcp_server
    from agent_kanban.auth import Principal

    async def _matching(agent):
        if agent != "codex":
            raise PermissionError(f"agent {agent!r} != 'codex'")
        return Principal(kind="token", agent_name="codex")

    async def _any():
        return Principal(kind="token", agent_name="codex")

    monkeypatch.setattr(mcp_server, "_require_matching_agent", _matching)
    monkeypatch.setattr(mcp_server, "_require_any_principal", _any)


@pytest_asyncio.fixture
async def authed_client(db_url):
    """An httpx AsyncClient with a logged-in admin session."""
    from agent_kanban.config import get_settings
    get_settings.cache_clear()
    from agent_kanban.server import create_app
    from agent_kanban.db import AsyncSessionLocal
    from agent_kanban.models import User
    from agent_kanban.auth import hash_password
    async with AsyncSessionLocal() as session:
        session.add(User(username="admin", password_hash=hash_password("pw"), is_admin=True))
        await session.commit()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await c.post("/api/login", json={"username": "admin", "password": "pw"})
        yield c
