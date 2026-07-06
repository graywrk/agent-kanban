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


# Module-level engine/session kept for backward-compat with any importer. The
# FastAPI dependency below resolves against current settings so overrides win.
engine = _engine_for(get_settings().database_url)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(
        _engine_for(get_settings().database_url),
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with factory() as session:
        yield session
