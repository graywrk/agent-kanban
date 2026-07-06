import pytest
from httpx import ASGITransport, AsyncClient

from agent_kanban.server import create_app


@pytest.fixture
async def client(db_url):
    from agent_kanban.config import get_settings

    get_settings.cache_clear()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_login_rate_limit_blocks_after_threshold(client):
    """When the limiter is enabled, the 11th login attempt in a minute is 429."""
    from agent_kanban.ratelimit import limiter

    # Reset the in-memory counter so prior tests don't count against us.
    limiter.reset()
    limiter.enabled = True
    try:
        # Hit /api/login 10 times (all will be 401 bad-creds, that's fine —
        # the limiter counts requests, not outcomes).
        for _ in range(10):
            r = await client.post("/api/login", json={"username": "x", "password": "x"})
            assert r.status_code == 401  # bad creds, but not rate-limited yet
        # 11th request must be rate-limited.
        r = await client.post("/api/login", json={"username": "x", "password": "x"})
        assert r.status_code == 429
    finally:
        limiter.enabled = False
        limiter.reset()
