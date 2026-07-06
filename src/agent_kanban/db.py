"""Async DB engine, session factory, and FastAPI dependency."""
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from agent_kanban.config import get_settings

# One engine per DATABASE_URL, reused across calls in a process. A test that
# points DATABASE_URL at a fresh throwaway DB gets its own engine; the production
# URL gets a single shared engine/pool. Keyed on the URL so env-var overrides win
# without invalidating an existing pool when the URL is unchanged.
_engines: dict[str, AsyncEngine] = {}


def _engine_for(url: str) -> AsyncEngine:
    engine = _engines.get(url)
    if engine is None:
        engine = create_async_engine(url, echo=False, pool_pre_ping=True)
        _engines[url] = engine
    return engine


def AsyncSessionLocal() -> AsyncSession:  # noqa: N802 - keep call-site name
    """Return an AsyncSession bound to the *current* DATABASE_URL.

    Resolving live (rather than pinning a sessionmaker at import time) ensures
    env-var overrides — e.g. per-test throwaway databases — take effect for any
    caller that imports this name, matching ``get_session``'s behaviour.
    """
    factory = async_sessionmaker(
        _engine_for(get_settings().database_url),
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return factory()


async def get_session() -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(
        _engine_for(get_settings().database_url),
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with factory() as session:
        yield session
