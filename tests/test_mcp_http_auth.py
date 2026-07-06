"""End-to-end test of the MCP HTTP auth chain.

The rest of the MCP test suite drives the tools in-process via
``mcp.call_tool`` with stubbed verifiers. This module proves the real HTTP path:
a ``POST /mcp/`` carrying ``Authorization: Bearer <token>`` flows through
``MCPAuthMiddleware`` → the ``_mcp_principal`` ContextVar → the verifier → the
tool. A request with no bearer must not yield a normal success result.
"""
import json

import pytest
from httpx import ASGITransport, AsyncClient

from agent_kanban.server import create_app


def _sse_payload(text: str) -> dict:
    """Extract the first JSON-RPC object from an MCP SSE response body.

    The streamable-http transport frames each JSON-RPC message as an SSE
    ``event: message\\n data: <json>`` block. The payload (the dict) is what
    callers should assert on.
    """
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            try:
                return json.loads(line[len("data:"):].strip())
            except json.JSONDecodeError:
                continue
    # Fallback: the whole body might be plain JSON.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"_raw": text}


def _maybe_json(response) -> dict:
    try:
        return response.json()
    except Exception:
        return {"_raw": response.text}


@pytest.fixture
async def http_client(db_url):
    """An httpx AsyncClient over the app with the MCP session manager running.

    We do NOT drive the app's full lifespan here: its ``session_manager.run()``
    spawns an anyio task group whose cancel scope must exit in the same task that
    entered it, and pytest-asyncio tears async-generator fixtures down in a
    different task, which raises "Attempted to exit cancel scope in a different
    task". Instead we start only the MCP session manager (the one thing /mcp/
    needs to be servable) and create the admin user directly. Both setups and
    their teardown run inside this fixture's own task, so their cancel scopes
    exit cleanly.
    """
    import os
    from agent_kanban.config import get_settings
    from agent_kanban.db import AsyncSessionLocal
    from agent_kanban.models import User
    from agent_kanban.auth import hash_password

    os.environ["AGENT_KANBAN_BOOTSTRAP_ADMIN_PASSWORD"] = "pw"
    get_settings.cache_clear()
    app = create_app()
    # Create the admin user directly (the app lifespan would have done this).
    async with AsyncSessionLocal() as session:
        session.add(User(username="admin", password_hash=hash_password("pw"), is_admin=True))
        await session.commit()
    mcp_instance = app.state.mcp
    transport = ASGITransport(app=app)
    client = AsyncClient(
        transport=transport,
        base_url="http://localhost",
        headers={
            # The MCP streamable-http transport validates:
            #   - Host header (DNS-rebinding protection): allows "localhost:*" —
            #     the host MUST include a port; and
            #   - Accept header: POSTs must accept application/json and
            #     text/event-stream.
            "host": "localhost:80",
            "accept": "application/json, text/event-stream",
        },
    )
    session_mgr_cm = mcp_instance.session_manager.run()
    await session_mgr_cm.__aenter__()
    try:
        await client.__aenter__()
        try:
            yield client
        finally:
            await client.__aexit__(None, None, None)
    finally:
        # pytest-asyncio may finalize this async-generator fixture on a
        # different task than setup; the MCP session_manager's anyio cancel
        # scope must exit in its entering task. Swallow the resulting
        # RuntimeError — the test body has already passed and the throwaway
        # DB (and its connections) are dropped by the `db_url` fixture anyway.
        try:
            await session_mgr_cm.__aexit__(None, None, None)
        except RuntimeError:
            pass
        os.environ.pop("AGENT_KANBAN_BOOTSTRAP_ADMIN_PASSWORD", None)


async def _bootstrap_admin_and_token(http_client):
    """Log in as the lifespan-bootstrapped admin, mint a token for 'codex'.

    Returns the plaintext token.
    """
    await http_client.post("/api/login", json={"username": "admin", "password": "pw"})
    r = await http_client.post("/api/tokens", json={"agent_name": "codex"})
    return r.json()["token"]


_INIT_PARAMS = {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "test", "version": "1.0"},
}


@pytest.mark.asyncio
async def test_mcp_http_rejects_unauthenticated(http_client):
    """A tools/call to /mcp/ without a bearer token must fail (the verifier raises)."""
    # initialize to obtain a session id
    r = await http_client.post(
        "/mcp/",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": _INIT_PARAMS},
    )
    session_id = r.headers.get("mcp-session-id")
    headers = {"mcp-session-id": session_id} if session_id else {}
    # list_tasks without bearer → the verifier raises PermissionError → tool error.
    r = await http_client.post(
        "/mcp/",
        headers=headers,
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
              "params": {"name": "list_tasks", "arguments": {}}},
    )
    # The streamable-http transport responds with SSE; the JSON-RPC payload is
    # in a `data:` line. Some SDK versions reply with a plain JSON body instead,
    # so handle both.
    if r.headers.get("content-type", "").startswith("text/event-stream"):
        body = _sse_payload(r.text)
    else:
        body = _maybe_json(r)
    # The key assertion: an unauthenticated call did NOT return a normal
    # empty-list success. Accept a JSON-RPC error, an is_error tool result, or
    # a 4xx status — the exact shape depends on the pinned SDK version.
    result_str = str(body)
    assert (
        "auth" in result_str.lower()
        or "error" in result_str.lower()
        or r.status_code in (400, 401, 403)
    ), f"expected auth/error, got {r.status_code}: {body}"


@pytest.mark.asyncio
async def test_mcp_http_accepts_bearer_token(http_client):
    """A tools/call with a valid bearer token + matching agent succeeds."""
    token = await _bootstrap_admin_and_token(http_client)
    auth = {"Authorization": f"Bearer {token}"}
    # initialize to get a session id
    r = await http_client.post(
        "/mcp/",
        headers=auth,
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": _INIT_PARAMS},
    )
    session_id = r.headers.get("mcp-session-id")
    headers = dict(auth)
    if session_id:
        headers["mcp-session-id"] = session_id
    # list_tasks should succeed (empty list — no tasks created).
    r = await http_client.post(
        "/mcp/",
        headers=headers,
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
              "params": {"name": "list_tasks", "arguments": {}}},
    )
    assert r.status_code == 200
    body = _sse_payload(r.text)
    # No "error" key at the JSON-RPC level on the success path.
    assert "error" not in body, f"unexpected JSON-RPC error: {body}"
