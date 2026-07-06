
import os

import asyncpg
import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from agent_kanban.server import create_app


async def _login_admin(client):
    """Create an admin user and log in so the TestClient carries the session cookie.

    Seed via raw asyncpg (not SQLAlchemy's AsyncSessionLocal) so we don't bind a
    pooled connection to this test loop — TestClient runs the app on its own
    event loop, and a cross-loop pooled connection crashes asyncpg.

    Uses ON CONFLICT (upsert) because the app lifespan now bootstraps an admin
    user on first run (empty users table); this resets its password to a known
    value so the subsequent login succeeds regardless of whether bootstrap ran.
    """
    from agent_kanban.auth import hash_password
    from datetime import UTC, datetime
    url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
    conn = await asyncpg.connect(url)
    try:
        await conn.execute(
            'INSERT INTO "user" (username, password_hash, is_admin, created_at) '
            "VALUES ($1, $2, $3, $4) "
            'ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash',
            "admin",
            hash_password("pw"),
            True,
            datetime.now(UTC).replace(tzinfo=None),
        )
    finally:
        await conn.close()
    client.post("/api/login", json={"username": "admin", "password": "pw"})


@pytest.mark.asyncio
async def test_ws_rejects_unauthenticated(db_url):
    """An unauthenticated WebSocket (no session cookie, no bearer) is rejected with code 1008."""
    from agent_kanban.config import get_settings
    get_settings.cache_clear()
    app = create_app()

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/ws"):
                pass
        assert exc.value.code == 1008


@pytest.mark.asyncio
async def test_ws_board_channel_receives_task_created(db_url):
    from agent_kanban.config import get_settings
    get_settings.cache_clear()
    app = create_app()

    with TestClient(app) as client:
        await _login_admin(client)
        with client.websocket_connect("/ws") as ws:
            # Trigger a task creation via REST.
            r = client.post("/api/tasks", json={"title": "x"})
            assert r.status_code == 201
            msg = ws.receive_json()
            assert msg["type"] == "task_created"
            assert msg["task_id"] == r.json()["id"]


@pytest.mark.asyncio
async def test_ws_task_channel_filtered(db_url):
    from agent_kanban.config import get_settings
    get_settings.cache_clear()
    app = create_app()

    with TestClient(app) as client:
        await _login_admin(client)
        # Create two tasks first.
        t1 = client.post("/api/tasks", json={"title": "a"}).json()
        t2 = client.post("/api/tasks", json={"title": "b"}).json()

        with client.websocket_connect(f"/ws?task_id={t1['id']}") as ws:
            # Comment on t2 — should NOT arrive on t1's channel.
            client.post(
                f"/api/tasks/{t2['id']}/comments",
                json={"author": "user", "content": "for t2"},
            )
            # Comment on t1 — SHOULD arrive.
            client.post(
                f"/api/tasks/{t1['id']}/comments",
                json={"author": "user", "content": "for t1"},
            )
            msg = ws.receive_json()
            assert msg["type"] == "comment"
            assert msg["author"] == "user"


@pytest.mark.asyncio
async def test_ws_accepts_ticket(db_url):
    """A single-use ticket from POST /api/ws-ticket authenticates the WS."""
    from agent_kanban.config import get_settings
    get_settings.cache_clear()
    app = create_app()

    with TestClient(app) as client:
        await _login_admin(client)
        # Mint a ticket via the authed REST endpoint.
        ticket = client.post("/api/ws-ticket").json()["ticket"]
        # Connecting with ?ticket= should be accepted and stream events.
        with client.websocket_connect(f"/ws?ticket={ticket}") as ws:
            r = client.post("/api/tasks", json={"title": "x"})
            assert r.status_code == 201
            msg = ws.receive_json()
            assert msg["type"] == "task_created"
            assert msg["task_id"] == r.json()["id"]


@pytest.mark.asyncio
async def test_ws_rejects_invalid_ticket(db_url):
    """A bogus ticket is rejected with code 1008."""
    from agent_kanban.config import get_settings
    get_settings.cache_clear()
    app = create_app()

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/ws?ticket=not-a-real-ticket"):
                pass
        assert exc.value.code == 1008
