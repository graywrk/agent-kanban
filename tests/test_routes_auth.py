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
async def test_setup_status_true_when_no_users(client):
    r = await client.get("/api/setup-status")
    assert r.status_code == 200
    assert r.json()["needs_setup"] is True


@pytest.mark.asyncio
async def test_login_rejects_bad_creds(client):
    # Create a user first via direct DB.
    from agent_kanban.db import AsyncSessionLocal
    from agent_kanban.models import User
    from agent_kanban.auth import hash_password
    async with AsyncSessionLocal() as session:
        session.add(User(username="alice", password_hash=hash_password("pw"), is_admin=True))
        await session.commit()
    r = await client.post("/api/login", json={"username": "alice", "password": "wrong"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_login_sets_cookie_and_me_works(client):
    from agent_kanban.db import AsyncSessionLocal
    from agent_kanban.models import User
    from agent_kanban.auth import hash_password
    async with AsyncSessionLocal() as session:
        session.add(User(username="alice", password_hash=hash_password("pw"), is_admin=True))
        await session.commit()
    r = await client.post("/api/login", json={"username": "alice", "password": "pw"})
    assert r.status_code == 200
    # Cookie should be set; httpx AsyncClient stores it.
    r = await client.get("/api/me")
    assert r.status_code == 200
    assert r.json()["agent_name"] == "user"
    assert r.json()["is_admin"] is True


@pytest.mark.asyncio
async def test_logout_clears_session(client):
    from agent_kanban.db import AsyncSessionLocal
    from agent_kanban.models import User
    from agent_kanban.auth import hash_password
    async with AsyncSessionLocal() as session:
        session.add(User(username="alice", password_hash=hash_password("pw"), is_admin=True))
        await session.commit()
    await client.post("/api/login", json={"username": "alice", "password": "pw"})
    await client.post("/api/logout")
    r = await client.get("/api/me")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_create_token_returns_plaintext_once(client):
    # Login as admin.
    from agent_kanban.db import AsyncSessionLocal
    from agent_kanban.models import User
    from agent_kanban.auth import hash_password
    async with AsyncSessionLocal() as session:
        session.add(User(username="alice", password_hash=hash_password("pw"), is_admin=True))
        await session.commit()
    await client.post("/api/login", json={"username": "alice", "password": "pw"})
    r = await client.post("/api/tokens", json={"agent_name": "codex", "description": "ci"})
    assert r.status_code == 201
    body = r.json()
    assert body["agent_name"] == "codex"
    assert isinstance(body["token"], str) and len(body["token"]) >= 32
    # Listing must NOT contain the plaintext token.
    r = await client.get("/api/tokens")
    assert all("token" not in t for t in r.json())


@pytest.mark.asyncio
async def test_token_authenticates_bearer(client):
    # Create a token, then use it as bearer to hit /api/me.
    from agent_kanban.db import AsyncSessionLocal
    from agent_kanban.models import User
    from agent_kanban.auth import hash_password
    async with AsyncSessionLocal() as session:
        session.add(User(username="alice", password_hash=hash_password("pw"), is_admin=True))
        await session.commit()
    await client.post("/api/login", json={"username": "alice", "password": "pw"})
    r = await client.post("/api/tokens", json={"agent_name": "codex"})
    token = r.json()["token"]
    # New client, no cookie, just bearer.
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as bearer_client:
        r = await bearer_client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["agent_name"] == "codex"
        assert r.json()["is_admin"] is False


@pytest.mark.asyncio
async def test_protected_route_401_without_creds(client):
    r = await client.get("/api/tasks")
    assert r.status_code == 401
