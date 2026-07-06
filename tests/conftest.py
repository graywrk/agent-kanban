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
