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


# --- Session secret detection (security guard, Fix 1) ---
def test_insecure_session_secret_detection():
    from agent_kanban.config import Settings

    assert (
        Settings(session_secret="dev-insecure-secret-change-me").is_insecure_session_secret()
        is True
    )
    assert (
        Settings(session_secret="please-change-me-in-production").is_insecure_session_secret()
        is True
    )
    assert Settings(session_secret="").is_insecure_session_secret() is True
    assert (
        Settings(session_secret="a-real-random-secret-32-chars-long").is_insecure_session_secret()
        is False
    )


# --- User-delete security guards (Fix 2) ---
@pytest.mark.asyncio
async def test_cannot_delete_self(client):
    from agent_kanban.db import AsyncSessionLocal
    from agent_kanban.models import User
    from agent_kanban.auth import hash_password

    async with AsyncSessionLocal() as session:
        session.add(User(username="admin", password_hash=hash_password("pw"), is_admin=True))
        await session.commit()
    await client.post("/api/login", json={"username": "admin", "password": "pw"})
    # /api/me returns the Principal; user_id is present for user principals.
    me = (await client.get("/api/me")).json()
    my_id = me["user_id"]
    r = await client.delete(f"/api/users/{my_id}")
    assert r.status_code == 400
    assert "yourself" in r.json().get("detail", "").lower()


@pytest.mark.asyncio
async def test_cannot_delete_last_admin(client):
    """Deleting the sole admin is blocked.

    When the caller is themselves the only admin, BOTH the self-guard
    ("cannot delete yourself") AND the last-admin guard ("cannot delete the
    last admin") would fire; the self-guard fires first and is what the test
    asserts on. This documents that the deletion path is rejected, exercising
    at least one of the two guards. Isolating the last-admin guard alone
    would require a second logged-in admin session (multi-session fixtures),
    which isn't trivial in this client-based setup.
    """
    from agent_kanban.db import AsyncSessionLocal
    from agent_kanban.models import User
    from agent_kanban.auth import hash_password

    async with AsyncSessionLocal() as session:
        session.add(User(username="admin", password_hash=hash_password("pw"), is_admin=True))
        await session.commit()
    await client.post("/api/login", json={"username": "admin", "password": "pw"})
    me = (await client.get("/api/me")).json()
    my_id = me["user_id"]
    # Deleting ourselves (the only admin) is rejected by both guards.
    r = await client.delete(f"/api/users/{my_id}")
    assert r.status_code == 400


# --- WebSocket ticket endpoint ---
@pytest.mark.asyncio
async def test_ws_ticket_requires_auth(client):
    r = await client.post("/api/ws-ticket")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_ws_ticket_minted_for_authed_user(client):
    from agent_kanban.db import AsyncSessionLocal
    from agent_kanban.models import User
    from agent_kanban.auth import hash_password

    async with AsyncSessionLocal() as session:
        session.add(User(username="alice", password_hash=hash_password("pw"), is_admin=True))
        await session.commit()
    await client.post("/api/login", json={"username": "alice", "password": "pw"})
    r = await client.post("/api/ws-ticket")
    assert r.status_code == 200
    body = r.json()
    assert "ticket" in body and len(body["ticket"]) >= 16
    assert body["expires_in"] == 60


@pytest.mark.asyncio
async def test_ws_ticket_single_use(client):
    """A ticket consumed by resolve_ticket cannot be reused."""
    from agent_kanban.auth import Principal, mint_ticket, resolve_ticket

    p = Principal(kind="user", agent_name="user", is_admin=True)
    nonce = mint_ticket(p)
    assert resolve_ticket(nonce) is not None
    assert resolve_ticket(nonce) is None  # consumed


# --- /api/setup + PATCH /api/users (Phase 5) ---
@pytest.mark.asyncio
async def test_setup_creates_first_admin(client):
    r = await client.post("/api/setup", json={"username": "root", "password": "hunter22"})
    assert r.status_code == 201
    # Now login works with those creds.
    r = await client.post("/api/login", json={"username": "root", "password": "hunter22"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_setup_rejected_after_users_exist(client):
    from agent_kanban.db import AsyncSessionLocal
    from agent_kanban.models import User
    from agent_kanban.auth import hash_password

    async with AsyncSessionLocal() as session:
        session.add(User(username="someone", password_hash=hash_password("pw"), is_admin=True))
        await session.commit()
    r = await client.post("/api/setup", json={"username": "root", "password": "hunter22"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_setup_rejects_empty_username(client):
    r = await client.post("/api/setup", json={"username": "  ", "password": "longenough"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_patch_user_changes_password(client):
    from agent_kanban.db import AsyncSessionLocal
    from agent_kanban.models import User
    from agent_kanban.auth import hash_password

    async with AsyncSessionLocal() as session:
        session.add(User(username="alice", password_hash=hash_password("old"), is_admin=True))
        await session.commit()
    await client.post("/api/login", json={"username": "alice", "password": "old"})
    r = await client.patch("/api/users/1", json={"current_password": "old", "password": "newpassword"})
    assert r.status_code == 200
    # New password works.
    r = await client.post("/api/login", json={"username": "alice", "password": "newpassword"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_patch_user_rejects_wrong_current_password(client):
    from agent_kanban.db import AsyncSessionLocal
    from agent_kanban.models import User
    from agent_kanban.auth import hash_password

    async with AsyncSessionLocal() as session:
        session.add(User(username="alice", password_hash=hash_password("old"), is_admin=True))
        await session.commit()
    await client.post("/api/login", json={"username": "alice", "password": "old"})
    r = await client.patch("/api/users/1", json={"current_password": "wrong", "password": "newpassword"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_patch_user_toggle_admin(client):
    from agent_kanban.db import AsyncSessionLocal
    from agent_kanban.models import User
    from agent_kanban.auth import hash_password

    async with AsyncSessionLocal() as session:
        admin = User(username="admin", password_hash=hash_password("pw"), is_admin=True)
        pleb = User(username="pleb", password_hash=hash_password("pw"), is_admin=False)
        session.add(admin)
        session.add(pleb)
        await session.commit()
        await session.refresh(pleb)
        pleb_id = pleb.id
    await client.post("/api/login", json={"username": "admin", "password": "pw"})
    r = await client.patch(f"/api/users/{pleb_id}", json={"is_admin": True})
    assert r.status_code == 200
    assert r.json()["is_admin"] is True
