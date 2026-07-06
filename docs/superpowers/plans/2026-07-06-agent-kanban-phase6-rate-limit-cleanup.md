# Agent Kanban — Phase 6 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add rate limiting to the unauthenticated-and-cheap-to-call endpoints, remove the deprecated `?token=` WebSocket fallback, and close the remaining test-coverage gaps from Phase 5 reviews.

**Architecture:** `slowapi` provides decorator-based per-IP rate limits backed by an in-memory token bucket (single-worker Phase 6; Redis backend is a config swap later). Limits apply to `/api/login`, `/api/setup`, and `/api/ws-ticket` — the public-or-cheap surface where brute-force/abuse matters. Removing `?token=` simplifies ws.py to ticket-or-cookie only. Test gaps are filled with targeted assertions.

**Tech Stack:** Python 3.11 + FastAPI (existing); `slowapi>=0.1.9` (new dep). No DB changes, no frontend changes.

**Spec:** N/A — hardening, not new features. The Phase 5 spec §5.4 already mentions WS tickets as the canonical WS auth; removing `?token=` aligns the code with that.

## Global Constraints

- All Phase 1–5 constraints still apply (Python 3.11+, PostgreSQL on host port **5436**, single-worker uvicorn, default port 7331).
- **No DB migrations.** No schema changes.
- **One new dependency:** `slowapi>=0.1.9`. In-memory backend (single-process); document Redis as the multi-worker upgrade path.
- Rate limits are **per-IP** (slowapi's default keying). Behind a reverse proxy, `X-Forwarded-For` must be trusted — document this.
- Rate limits: `/api/login` 10/min, `/api/setup` 5/min, `/api/ws-ticket` 30/min. Tunable via config.
- `?token=` WS param removed entirely; ticket-or-cookie only.
- TDD for backend.

---

## File Structure

```
src/agent_kanban/
├── ratelimit.py         # CREATE: limiter instance + dependency + get_remote_address helper
├── config.py            # MODIFY: rate_limit_{login,setup,ws_ticket} settings
├── routes/auth.py       # MODIFY: @limiter.limit on login/setup/ws-ticket
├── routes/ws.py         # MODIFY: remove ?token= param + bearer fallback
└── server.py            # MODIFY: register SlowAPIMiddleware + exception handler
tests/
├── test_ratelimit.py    # CREATE: limiter blocks after N calls
├── test_routes_auth.py  # MODIFY: existing tests still pass under limits (limiter disabled in tests)
└── test_ws.py           # MODIFY: assert ?token= is gone (rejected); ticket still works
pyproject.toml           # MODIFY: add slowapi
```

---

## Task 1: slowapi integration + rate limits on login/setup/ws-ticket

**Files:**
- Modify: `pyproject.toml` (add `slowapi>=0.1.9`)
- Create: `src/agent_kanban/ratelimit.py`
- Modify: `src/agent_kanban/config.py`
- Modify: `src/agent_kanban/server.py`
- Modify: `src/agent_kanban/routes/auth.py`
- Create: `tests/test_ratelimit.py`

**Interfaces:**
- Produces: `agent_kanban.ratelimit.limiter` (a `Limiter` instance). Config keys `rate_limit_login`, `rate_limit_setup`, `rate_limit_ws_ticket` (strings like `"10/minute"`, used as documentation; the decorator values are literals per slowapi's import-time decoration model).

- [ ] **Step 1: Add the dependency**

In `pyproject.toml` `[project] dependencies`, add:
```toml
    "slowapi>=0.1.9",
```
Run: `uv sync --extra dev`

- [ ] **Step 2: Create `ratelimit.py`**

Create `src/agent_kanban/ratelimit.py`:
```python
"""Rate limiting via slowapi (in-memory token bucket, single-process).

For multi-worker deployments, swap the storage_uri to a Redis URL:
    limiter = Limiter(storage_uri="redis://localhost:6379")
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")
```

- [ ] **Step 3: Add config keys**

In `src/agent_kanban/config.py`, add to `Settings`:
```python
    rate_limit_login: str = "10/minute"
    rate_limit_setup: str = "5/minute"
    rate_limit_ws_ticket: str = "30/minute"
```

- [ ] **Step 4: Register slowapi in `server.py`**

Open `src/agent_kanban/server.py`. Add imports:
```python
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from agent_kanban.ratelimit import limiter
```
In `create_app()`, AFTER `app = FastAPI(...)` but BEFORE routers are included:
```python
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
```

- [ ] **Step 5: Decorate the three endpoints**

In `src/agent_kanban/routes/auth.py`, add at the top:
```python
from agent_kanban.ratelimit import limiter
```
slowapi's `@limiter.limit(...)` decorator requires the route function to have a `request: Request` parameter (any name, but slowapi looks for one annotated as `Request`). The login and ws-ticket handlers already take `request: Request`; setup does not — add it.

Decorate:
```python
@router.post("/login")
@limiter.limit(settings.rate_limit_login)
async def login(body: LoginBody, request: Request, session: AsyncSession = Depends(get_session)):
    ...

@router.post("/setup", status_code=201)
@limiter.limit(settings.rate_limit_setup)
async def setup(body: SetupBody, request: Request, session: AsyncSession = Depends(get_session)):
    ...

@router.post("/ws-ticket")
@limiter.limit(settings.rate_limit_ws_ticket)
async def ws_ticket(request: Request, principal: Principal = Depends(get_current_principal)):
    ...
```

**Important:** `settings` must be resolved at decoration time, but the decorator runs at import. Use a literal string OR resolve settings inside a callable. The clean approach: use the literal default strings in the decorator and override via `default_limits` if needed. Simplest correct version:
```python
@limiter.limit("10/minute")
async def login(...):
```
(You can read `settings.rate_limit_login` at call time inside the handler for other purposes, but the decorator value is static.) Use the literal strings to avoid import-time settings resolution.

- [ ] **Step 6: Disable the limiter in the test suite**

slowapi's in-memory limiter would make test runs that loop login/logout hit the limit. The clean fix: set `limiter.enabled = False` in a conftest fixture. In `tests/conftest.py`, add an autouse fixture:
```python
@pytest.fixture(autouse=True)
def _disable_rate_limiting():
    """Disable slowapi in tests so suite-wide auth flows don't trip limits."""
    from agent_kanban.ratelimit import limiter
    saved = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = saved
```

- [ ] **Step 7: Write a test that the limiter works when enabled**

Create `tests/test_ratelimit.py`:
```python
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
async def test_login_rate_limit_blocks_after_threshold(client, monkeypatch):
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
```

> **Note:** `limiter.reset()` clears the in-memory storage. If the pinned slowapi version doesn't expose `reset`, clear via `limiter._storage.storage.clear()` or `limiter.storage.reset()`. Inspect the API and adapt. The key assertions: 10 succeed (401), 11th is 429.

- [ ] **Step 8: Run tests + commit**

Run: `uv run pytest -v`
Expected: all passing including the new rate-limit test. Existing tests pass because the autouse fixture disables the limiter.

```bash
git add -A
git commit -m "feat(ratelimit): slowapi on /api/login, /api/setup, /api/ws-ticket"
```

---

## Task 2: Remove deprecated `?token=` WS param

**Files:**
- Modify: `src/agent_kanban/routes/ws.py`
- Modify: `tests/test_ws.py`

- [ ] **Step 1: Strip the `token` param and bearer fallback from ws.py**

Replace `src/agent_kanban/routes/ws.py` with:
```python
"""WebSocket endpoint for live updates."""
from contextlib import suppress
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from agent_kanban.auth import _resolve_cookie, resolve_ticket
from agent_kanban.db import AsyncSessionLocal
from agent_kanban.events import event_bus

router = APIRouter(tags=["ws"])


@router.websocket("/ws")
async def ws_endpoint(
    websocket: WebSocket,
    task_id: Optional[int] = None,
    ticket: Optional[str] = Query(None, description="Single-use WS ticket from POST /api/ws-ticket"),
):
    # 1. Ticket path (preferred) — no DB hit, single-use nonce.
    if ticket:
        principal = resolve_ticket(ticket)
        if principal is not None:
            await websocket.accept()
            await _stream(websocket, task_id)
            return
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 2. Session cookie fallback (same-origin deployments).
    async with AsyncSessionLocal() as session:
        user_id = websocket.session.get("user_id") if hasattr(websocket, "session") else None
        ok = user_id is not None and (await _resolve_cookie(session, int(user_id))) is not None
    if not ok:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()
    await _stream(websocket, task_id)


async def _stream(websocket: WebSocket, task_id: Optional[int]) -> None:
    channel = f"task:{task_id}" if task_id else "board"
    subscriber = event_bus.subscribe(channel)
    try:
        async for evt in subscriber:
            with suppress(Exception):
                await websocket.send_json(evt)
    except WebSocketDisconnect:
        pass
    finally:
        with suppress(Exception):
            await subscriber.aclose()
```

(Imports of `_resolve_bearer` and `Query` for `token` are removed. The `Query` import stays because `ticket` still uses it.)

- [ ] **Step 2: Add a test asserting `?token=` is now rejected**

In `tests/test_ws.py`, add:
```python
def test_ws_token_param_no_longer_accepted(db_url):
    """Phase 6 removed ?token=; a bearer in the URL no longer authenticates the WS."""
    from agent_kanban.config import get_settings
    get_settings.cache_clear()
    from agent_kanban.db import AsyncSessionLocal
    from agent_kanban.models import User, Token
    from agent_kanban.auth import hash_password, hash_token
    app = create_app()
    # Seed a user + a token.
    import asyncio
    async def seed():
        async with AsyncSessionLocal() as session:
            u = User(username="admin", password_hash=hash_password("pw"), is_admin=True)
            session.add(u)
            await session.commit()
            await session.refresh(u)
            session.add(Token(agent_name="codex", token_hash=hash_token("abc1234567890123456789012345678901234567"), token_prefix="abc12345", created_by_user_id=u.id))
            await session.commit()
    asyncio.get_event_loop().run_until_complete(seed()) if False else None
    # The TestClient runs its own loop; use the same login helper pattern.
    from starlette.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect
    with TestClient(app) as client:
        client.post("/api/login", json={"username": "admin", "password": "pw"})
        # Mint a real token to use in the URL (proves it's rejected even when valid).
        r = client.post("/api/tokens", json={"agent_name": "codex"})
        bearer = r.json()["token"]
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect(f"/ws?token={bearer}"):
                pass
        assert exc.value.code == 1008
```

> **Note for the implementer:** the seeding helper above is awkward because `TestClient` and the async seed run on different loops. Follow the EXACT pattern used by the existing `_login_admin` helper in `test_ws.py` (which already solves this — it uses raw asyncpg to avoid the cross-loop issue). Replicate that pattern to seed the user, login via TestClient, mint a token via the API, then attempt `?token=`. The assertion is: `WebSocketDisconnect` with `code == 1008`. If TestClient carries the session cookie and the cookie path accepts, the WS may succeed — in that case the test proves the cookie path still works and the `?token=` param is simply ignored. To isolate the `?token=` rejection, you need a fresh client WITHOUT the cookie. Use a second `TestClient(app)` instance that doesn't login, then `?token=` alone must 1008. Adapt accordingly and document.

- [ ] **Step 3: Run tests + commit**

Run: `uv run pytest -v`
Expected: all passing.

```bash
git add -A
git commit -m "chore(ws): remove deprecated ?token= param; ticket-or-cookie only"
```

---

## Task 3: Close test-coverage gaps from Phase 5 reviews

**Files:**
- Modify: `tests/test_routes_auth.py` (acting-vs-target PATCH password test)
- Modify: `tests/test_auth.py` (legacy empty-prefix fallback test)

- [ ] **Step 1: Acting-vs-target PATCH password test**

In `tests/test_routes_auth.py`, add a test where admin A changes user B's password using A's current_password (NOT B's):
```python
@pytest.mark.asyncio
async def test_patch_user_password_uses_acting_admin_current_password(client):
    """PATCH user password verifies current_password against the ACTING admin, not the target."""
    from agent_kanban.db import AsyncSessionLocal
    from agent_kanban.models import User
    from agent_kanban.auth import hash_password
    async with AsyncSessionLocal() as session:
        admin = User(username="admin", password_hash=hash_password("adminpw"), is_admin=True)
        pleb = User(username="pleb", password_hash=hash_password("plebpw"), is_admin=False)
        session.add(admin); session.add(pleb)
        await session.commit()
        await session.refresh(admin); await session.refresh(pleb)
        admin_id, pleb_id = admin.id, pleb.id
    # Login as admin.
    await client.post("/api/login", json={"username": "admin", "password": "adminpw"})
    # Try to change pleb's password using PLEB's current_password (must fail — 403).
    r = await client.patch(f"/api/users/{pleb_id}", json={"current_password": "plebpw", "password": "newpass123"})
    assert r.status_code == 403
    # Now change pleb's password using ADMIN's current_password (must succeed).
    r = await client.patch(f"/api/users/{pleb_id}", json={"current_password": "adminpw", "password": "newpass123"})
    assert r.status_code == 200
    # pleb can now log in with the new password.
    r = await client.post("/api/login", json={"username": "pleb", "password": "newpass123"})
    assert r.status_code == 200
```

- [ ] **Step 2: Legacy empty-prefix fallback test**

In `tests/test_auth.py`, add:
```python
@pytest.mark.asyncio
async def test_resolve_bearer_falls_back_for_legacy_empty_prefix(session):
    """Tokens minted before Phase 5 (empty token_prefix) still resolve via full scan."""
    from agent_kanban.auth import _resolve_bearer, generate_token, hash_token
    from agent_kanban.models import Token
    plain = generate_token()
    # Legacy row: token_prefix not set (empty string).
    session.add(Token(agent_name="legacy", token_hash=hash_token(plain), token_prefix="", created_by_user_id=1))
    await session.commit()
    p = await _resolve_bearer(session, plain)
    assert p is not None
    assert p.agent_name == "legacy"
```

(Note: `created_by_user_id=1` requires a user with id=1; if the FK constraint complains, seed a user first. The conftest `session` fixture uses a fresh DB so there's no user; either seed one or use a value that satisfies the FK. The cleanest is to create a user row first in the test.)

- [ ] **Step 3: Run tests + commit**

Run: `uv run pytest -v`
Expected: all passing.

```bash
git add -A
git commit -m "test(auth): acting-vs-target password, legacy prefix fallback"
```

---

## Phase 6 Acceptance Criteria

- [ ] `uv run pytest -v` passes (102 prior + new tests).
- [ ] `cd web && pnpm build` succeeds (no frontend changes; sanity check).
- [ ] `uv run ruff check src/ tests/` is clean.
- [ ] `/api/login`, `/api/setup`, `/api/ws-ticket` return 429 after their per-minute thresholds when the limiter is enabled.
- [ ] The limiter is disabled in the test suite (autouse fixture) so existing tests don't trip.
- [ ] `?token=` WS param is removed; ws.py accepts only `?ticket=` or session cookie.
- [ ] PATCH user password test proves current_password is verified against the acting admin, not the target.
- [ ] Legacy empty-prefix token resolves via the full-scan fallback.
- [ ] No DB migrations added.

---

## Notes for the implementer

- **slowapi is alpha-quality** per its docs, but it's the de-facto FastAPI rate-limit lib and the API has been stable. Pin `>=0.1.9`. For production multi-worker, swap `storage_uri="memory://"` for a Redis URL and document it.
- **The `@limiter.limit` decorator needs the route to have a `request: Request` parameter.** The login and ws-ticket handlers already take `request`; setup does not — add it (FastAPI injects it; slowapi reads it).
- **Per-IP keying behind a reverse proxy** requires trusting `X-Forwarded-For`. slowapi's `get_remote_address` reads the socket peer by default; for proxy deployments, swap the `key_func` to parse `X-Forwarded-For`. Document this in the README's deployment section if you touch it.
- **`limiter.reset()`** clears in-memory state between tests. If the API differs in your pinned version, inspect `limiter._storage` and clear manually.
- **The `?token=` removal is a breaking change** for any agent/script that used bearer-in-URL. The README already documents the ticket flow (Phase 5); no migration path is needed beyond that.
- **Rate limits are intentionally lenient** (10/min login, 5/min setup, 30/min ws-ticket). A legitimate user rarely hits these; an attacker brute-forcing login will. Tune via config if needed.
