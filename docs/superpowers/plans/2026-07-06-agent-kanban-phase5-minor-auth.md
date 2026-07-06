# Agent Kanban — Phase 5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close out the deferred Phase 4 review findings: replace the WS bearer-in-URL with a short-lived ticket, add `PATCH /api/users/{id}` and `POST /api/setup`, enable CORS credentials, optimize token lookup with a prefix index — and update the spec + README to reflect that the board is no longer "no auth."

**Architecture:** Small additive changes on the merged Phase 4 auth layer. The WS ticket is a single-row in-memory dict (Phase 5 is single-process; Redis later if horizontal). The token prefix index adds a column + migration. `/api/setup` is gated by the existing `setup-status` check. Documentation updates are prose only.

**Tech Stack:** Python 3.11 + FastAPI + sqlmodel + alembic (existing); React/Vite/TS (existing). No new dependencies.

**Spec:** Updates `docs/superpowers/specs/2026-07-05-agent-kanban-design.md` §5.3 (was "no auth"; now describes the Phase 4 model) and adds §5.4 (WS tickets), §5.5 (setup endpoint). The spec's "single-user, no auth" stance is officially superseded.

## Global Constraints

- All Phase 1–4 constraints still apply (Python 3.11+, PostgreSQL on host port **5436**, MCP SDK `mcp>=1.27,<2.0`, default port 7331, bcrypt cost 12).
- **One DB migration** (`0003_phase5.py`): adds `token.token_prefix` (indexed, first 8 chars of the plaintext) + backfills existing rows with `""` (their plaintext is unknown, so they keep working via the full-scan fallback).
- **No new dependencies.**
- WS tickets live in an in-memory dict keyed by nonce; expire after 60s; single-use.
- `/api/setup` is only valid when `needs_setup` is true (zero users). Once any user exists, it returns 409.
- CORS `allow_credentials=True` requires `allow_origins` to be explicit (no `*`). The default `["http://localhost:5173"]` is explicit, so this is safe; document that prod must set the real origin.
- TDD for backend; `pnpm build` for frontend; prose review for docs.

---

## File Structure

```
src/agent_kanban/
├── models.py            # MODIFY: Token gains token_prefix (indexed)
├── auth.py              # MODIFY: _resolve_bearer filters by prefix; add mint_ticket/resolve_ticket
├── routes/
│   ├── auth.py          # MODIFY: add POST /api/setup, PATCH /api/users/{id}, POST /api/ws-ticket
│   └── ws.py            # MODIFY: accept ?ticket= alongside ?token= (ticket preferred)
├── server.py            # MODIFY: CORS allow_credentials=True
migrations/versions/
└── 0003_phase5.py       # CREATE: token_prefix column + index
tests/
├── test_auth.py         # MODIFY: prefix-filtered resolution; ticket mint/resolve/expiry
├── test_routes_auth.py  # MODIFY: setup endpoint, PATCH user, ws-ticket
└── test_ws.py           # MODIFY: ticket-based auth path
web/src/
├── api.ts               # MODIFY: fetchWsTicket, setup, updateUser; WS uses ticket
├── pages/
│   ├── Login.tsx        # MODIFY: real setup flow (POST /api/setup instead of advisory)
│   └── Admin.tsx        # MODIFY: edit-user form (password + admin toggle)
docs/superpowers/specs/
└── 2026-07-05-agent-kanban-design.md  # MODIFY: §5.3 rewrite, add §5.4/§5.5
README.md                # MODIFY: reflect auth (already mostly done in Phase 4)
```

---

## Task 1: Token prefix index + migration

Optimize `_resolve_bearer` from O(N) bcrypt scan to O(1) index lookup + 1 bcrypt verify.

**Files:**
- Modify: `src/agent_kanban/models.py` (add `token_prefix`)
- Create: `migrations/versions/0003_phase5.py`
- Modify: `src/agent_kanban/auth.py` (`_resolve_bearer` filters by prefix; `create_token`-equivalent sets prefix)
- Modify: `src/agent_kanban/routes/auth.py` (set `token_prefix` when minting)
- Modify: `tests/test_auth.py`

**Interfaces:**
- Produces: `Token.token_prefix: str` (first 8 chars of the plaintext token, indexed). `_resolve_bearer` does `WHERE token_prefix = ?` then bcrypt-verifies the (typically 1) candidate.

- [ ] **Step 1: Add the column to the model**

In `src/agent_kanban/models.py`, in the `Token` class, add after `token_hash`:
```python
    token_prefix: str = Field(default="", index=True)  # first 8 chars of plaintext, for fast lookup
```

- [ ] **Step 2: Generate the migration**

Run:
```bash
uv run alembic revision --autogenerate -m "phase5: token_prefix column + index"
```
Rename to `0003_phase5.py`. Open it and verify it only adds the `token_prefix` column + index to the `token` table with `server_default=""` and `nullable=False`. Remove any spurious alter_column noise on other tables (autogenerate sometimes emits JSONB rendering drift).

- [ ] **Step 3: Round-trip the migration**

```bash
docker exec ak-pg psql -U kanban -d postgres -c "DROP DATABASE IF EXISTS kanban;"
docker exec ak-pg psql -U kanban -d postgres -c "CREATE DATABASE kanban OWNER kanban;"
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```
Expected: all three succeed.

- [ ] **Step 4: Set token_prefix at mint time**

In `src/agent_kanban/routes/auth.py`, in the `create_token` handler, when building the `Token` row, set the prefix:
```python
    plain = generate_token()
    tok = Token(
        agent_name=body.agent_name,
        token_hash=hash_token(plain),
        token_prefix=plain[:8],
        description=body.description,
        created_by_user_id=principal.user_id,
    )
```

- [ ] **Step 5: Update `_resolve_bearer` to filter by prefix**

In `src/agent_kanban/auth.py`, replace `_resolve_bearer` with:
```python
async def _resolve_bearer(session: AsyncSession, header_value: str) -> Optional[Principal]:
    """Look up a Token row whose hash matches the bearer value.

    Filters by the first-8-char prefix (indexed) before bcrypt-verifying, so
    the typical cost is one index lookup + one bcrypt check instead of N.
    Falls back to a full scan if the prefix column is empty (legacy rows
    whose plaintext was lost), so existing tokens keep working.
    """
    prefix = header_value[:8]
    # Try the prefix-filtered path first.
    stmt = select(Token).where(Token.token_prefix == prefix)
    result = await session.execute(stmt)
    candidates = list(result.scalars())
    if not candidates:
        # Fallback: legacy rows with empty prefix.
        legacy_stmt = select(Token).where(Token.token_prefix == "")
        legacy_result = await session.execute(legacy_stmt)
        candidates = list(legacy_result.scalars())
    for row in candidates:
        if verify_token(header_value, row.token_hash):
            row.last_used_at = datetime.now(UTC).replace(tzinfo=None)
            await session.commit()
            return Principal(
                kind="token",
                agent_name=row.agent_name,
                is_admin=False,
            )
    return None
```

- [ ] **Step 6: Add tests**

In `tests/test_auth.py`, add:
```python
@pytest.mark.asyncio
async def test_resolve_bearer_uses_prefix_filter(session):
    """The prefix index narrows candidates before bcrypt."""
    from agent_kanban.auth import _resolve_bearer, generate_token, hash_token
    from agent_kanban.models import Token
    # Two tokens with different prefixes.
    t1 = generate_token()
    t2 = generate_token()
    session.add(Token(agent_name="a", token_hash=hash_token(t1), token_prefix=t1[:8]))
    session.add(Token(agent_name="b", token_hash=hash_token(t2), token_prefix=t2[:8]))
    await session.commit()
    p = await _resolve_bearer(session, t1)
    assert p is not None and p.agent_name == "a"
    p = await _resolve_bearer(session, t2)
    assert p is not None and p.agent_name == "b"
    p = await _resolve_bearer(session, "not-a-real-token")
    assert p is None
```

- [ ] **Step 7: Run tests + commit**

Run: `uv run pytest -v`
Expected: all passing.

```bash
git add -A
git commit -m "perf(auth): token prefix index for O(1) bearer lookup"
```

---

## Task 2: WebSocket ticket endpoint + ws.py ticket auth

Replace the `?token=<bearer>` WS auth with `?ticket=<nonce>`: the frontend POSTs `/api/ws-ticket` (authenticated) to get a single-use nonce valid for 60s, then connects the WS with `?ticket=`. The bearer never appears in URL logs.

**Files:**
- Modify: `src/agent_kanban/auth.py` (add `mint_ticket`, `resolve_ticket` — in-memory dict with expiry)
- Modify: `src/agent_kanban/routes/auth.py` (add `POST /api/ws-ticket`)
- Modify: `src/agent_kanban/routes/ws.py` (accept `?ticket=`; prefer it over `?token=`; keep `?token=` as fallback for one release)
- Modify: `tests/test_routes_auth.py`, `tests/test_ws.py`

**Interfaces:**
- Produces: `POST /api/ws-ticket` (requires principal) → `{ticket: "<nonce>", expires_in: 60}`. `mint_ticket(principal) -> str`, `resolve_ticket(nonce) -> Optional[Principal]` (consumes the nonce).

- [ ] **Step 1: Implement the ticket store in `auth.py`**

Append to `src/agent_kanban/auth.py`:
```python
import time

# In-process WS ticket store. Keyed by nonce, value (Principal, expiry_ts).
# Single-process Phase 5; Redis if we ever scale horizontally.
_WS_TICKETS: dict[str, tuple[Principal, float]] = {}
_WS_TICKET_TTL_S = 60.0


def mint_ticket(principal: Principal) -> str:
    """Issue a single-use WS ticket bound to the given principal. Valid 60s."""
    nonce = secrets.token_urlsafe(16)
    _WS_TICKETS[nonce] = (principal, time.monotonic() + _WS_TICKET_TTL_S)
    return nonce


def resolve_ticket(nonce: str) -> Optional[Principal]:
    """Consume a WS ticket. Returns the Principal if valid+unexpired, else None.

    Single-use: the nonce is removed regardless of outcome so a replay fails.
    """
    _gc_tickets()
    entry = _WS_TICKETS.pop(nonce, None)
    if entry is None:
        return None
    principal, expires_at = entry
    if time.monotonic() > expires_at:
        return None
    return principal


def _gc_tickets() -> None:
    """Drop expired tickets so the dict doesn't grow unbounded."""
    now = time.monotonic()
    expired = [k for k, (_, exp) in _WS_TICKETS.items() if now > exp]
    for k in expired:
        _WS_TICKETS.pop(k, None)
```

(`secrets` is already imported at the top of auth.py from `generate_token`.)

- [ ] **Step 2: Add the `POST /api/ws-ticket` route**

In `src/agent_kanban/routes/auth.py`, after the `me` endpoint, add:
```python
@router.post("/ws-ticket")
async def ws_ticket(principal: Principal = Depends(get_current_principal)):
    """Mint a single-use ticket for WebSocket authentication.

    The WS cannot set Authorization headers (browser limitation), so for
    cross-origin WS the frontend posts this endpoint (cookie/bearer authed)
    and connects the socket with ?ticket=<nonce>. The nonce is single-use
    and expires in 60s, so it never leaks the bearer into proxy logs.
    """
    from agent_kanban.auth import mint_ticket
    return {"ticket": mint_ticket(principal), "expires_in": 60}
```

- [ ] **Step 3: Update `ws.py` to accept `?ticket=`**

Replace `src/agent_kanban/routes/ws.py` with:
```python
"""WebSocket endpoint for live updates."""
from contextlib import suppress
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from agent_kanban.auth import _resolve_bearer, _resolve_cookie, resolve_ticket
from agent_kanban.db import AsyncSessionLocal
from agent_kanban.events import event_bus

router = APIRouter(tags=["ws"])


@router.websocket("/ws")
async def ws_endpoint(
    websocket: WebSocket,
    task_id: Optional[int] = None,
    ticket: Optional[str] = Query(None, description="Single-use WS ticket from POST /api/ws-ticket"),
    token: Optional[str] = Query(None, description="Bearer token (deprecated; use ticket)"),
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

    # 2. Session cookie or bearer fallback (same-origin / legacy).
    async with AsyncSessionLocal() as session:
        user_id = websocket.session.get("user_id") if hasattr(websocket, "session") else None
        ok = False
        if user_id is not None:
            ok = (await _resolve_cookie(session, int(user_id))) is not None
        if not ok and token:
            ok = (await _resolve_bearer(session, token)) is not None
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

- [ ] **Step 4: Add tests**

In `tests/test_routes_auth.py`, add:
```python
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
    from agent_kanban.auth import mint_ticket, resolve_ticket, Principal
    p = Principal(kind="user", agent_name="user", is_admin=True)
    nonce = mint_ticket(p)
    assert resolve_ticket(nonce) is not None
    assert resolve_ticket(nonce) is None  # consumed
```

In `tests/test_ws.py`, add a test that connects with a ticket. Adapt the existing login helper; after login, mint a ticket via POST /api/ws-ticket, then `websocket_connect(f"/ws?ticket={ticket}")`.

- [ ] **Step 5: Run tests + commit**

Run: `uv run pytest -v`
Expected: all passing.

```bash
git add -A
git commit -m "feat(ws): single-use ticket auth (replaces bearer-in-URL)"
```

---

## Task 3: `POST /api/setup` + `PATCH /api/users/{id}`

Replace the brittle "read password from stdout" first-run with an in-app setup endpoint, and add user editing (password change + admin toggle).

**Files:**
- Modify: `src/agent_kanban/routes/auth.py`
- Modify: `tests/test_routes_auth.py`

**Interfaces:**
- Produces: `POST /api/setup` (valid only when `needs_setup`; creates the first admin; 409 otherwise) and `PATCH /api/users/{id}` (admin; body `{password?, is_admin?}`; password requires `current_password` of the acting admin OR the target being the acting user with correct current_password).

- [ ] **Step 1: Write failing tests**

In `tests/test_routes_auth.py`, add:
```python
@pytest.mark.asyncio
async def test_setup_creates_first_admin(client):
    r = await client.post("/api/setup", json={"username": "root", "password": "hunter2"})
    assert r.status_code == 201
    # Now login works with those creds.
    r = await client.post("/api/login", json={"username": "root", "password": "hunter2"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_setup_rejected_after_users_exist(client):
    from agent_kanban.db import AsyncSessionLocal
    from agent_kanban.models import User
    from agent_kanban.auth import hash_password
    async with AsyncSessionLocal() as session:
        session.add(User(username="someone", password_hash=hash_password("pw"), is_admin=True))
        await session.commit()
    r = await client.post("/api/setup", json={"username": "root", "password": "hunter2"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_patch_user_changes_password(client):
    from agent_kanban.db import AsyncSessionLocal
    from agent_kanban.models import User
    from agent_kanban.auth import hash_password, verify_password
    async with AsyncSessionLocal() as session:
        session.add(User(username="alice", password_hash=hash_password("old"), is_admin=True))
        await session.commit()
    await client.post("/api/login", json={"username": "alice", "password": "old"})
    r = await client.patch("/api/users/1", json={"current_password": "old", "password": "new"})
    assert r.status_code == 200
    # New password works.
    r = await client.post("/api/login", json={"username": "alice", "password": "new"})
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
    r = await client.patch("/api/users/1", json={"current_password": "wrong", "password": "new"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_patch_user_toggle_admin(client):
    from agent_kanban.db import AsyncSessionLocal
    from agent_kanban.models import User
    from agent_kanban.auth import hash_password
    async with AsyncSessionLocal() as session:
        admin = User(username="admin", password_hash=hash_password("pw"), is_admin=True)
        pleb = User(username="pleb", password_hash=hash_password("pw"), is_admin=False)
        session.add(admin); session.add(pleb)
        await session.commit()
        await session.refresh(pleb)
        pleb_id = pleb.id
    await client.post("/api/login", json={"username": "admin", "password": "pw"})
    r = await client.patch(f"/api/users/{pleb_id}", json={"is_admin": True})
    assert r.status_code == 200
    assert r.json()["is_admin"] is True
```

- [ ] **Step 2: Implement `POST /api/setup`**

In `src/agent_kanban/routes/auth.py`, near `setup_status`, add:
```python
class SetupBody(BaseModel):
    username: str
    password: str


@router.post("/setup", status_code=201)
async def setup(body: SetupBody, session: AsyncSession = Depends(get_session)):
    """Create the first admin user. Only valid when no users exist (needs_setup)."""
    existing = (await session.execute(select(func.count(User.id)))).scalar_one()
    if existing > 0:
        raise HTTPException(409, "setup already complete — users exist")
    if len(body.password) < 8:
        raise HTTPException(400, "password must be at least 8 characters")
    u = User(username=body.username, password_hash=hash_password(body.password), is_admin=True)
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return {"id": u.id, "username": u.username, "is_admin": u.is_admin}
```

- [ ] **Step 3: Implement `PATCH /api/users/{id}`**

In `src/agent_kanban/routes/auth.py`, after `delete_user`, add:
```python
class UserPatch(BaseModel):
    current_password: Optional[str] = None
    password: Optional[str] = None
    is_admin: Optional[bool] = None


@router.patch("/users/{user_id}")
async def patch_user(
    user_id: int,
    body: UserPatch,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
):
    _require_admin(principal)
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(404, "user not found")

    if body.password is not None:
        # Password change requires the acting admin's current password.
        if not body.current_password:
            raise HTTPException(400, "current_password required to change password")
        acting = await session.get(User, principal.user_id)
        if acting is None or not verify_password(body.current_password, acting.password_hash):
            raise HTTPException(403, "current_password incorrect")
        if len(body.password) < 8:
            raise HTTPException(400, "password must be at least 8 characters")
        target.password_hash = hash_password(body.password)

    if body.is_admin is not None:
        # Demoting the last admin is forbidden.
        if body.is_admin is False and target.is_admin is True:
            admin_count = (
                await session.execute(select(func.count(User.id)).where(User.is_admin == True))  # noqa: E712
            ).scalar_one()
            if admin_count <= 1:
                raise HTTPException(400, "cannot demote the last admin")
        target.is_admin = body.is_admin

    await session.commit()
    await session.refresh(target)
    return {"id": target.id, "username": target.username, "is_admin": target.is_admin}
```

- [ ] **Step 4: Disable the stdout bootstrap now that /api/setup exists**

In `src/agent_kanban/server.py`, the `_bootstrap_admin` lifespan hook currently creates an admin from `BOOTSTRAP_ADMIN_PASSWORD` or a generated password. With `/api/setup`, the operator sets the password in-app. Keep the hook ONLY for the case where `BOOTSTRAP_ADMIN_PASSWORD` is explicitly set (env), so existing automation still works; remove the auto-generate-and-print path:

Replace the body of `_bootstrap_admin` with:
```python
    async def _bootstrap_admin():
        """Create an admin from BOOTSTRAP_ADMIN_PASSWORD if set and no users exist.

        If the env var is unset, first-run uses POST /api/setup from the UI instead.
        """
        from sqlmodel import select
        from agent_kanban.db import AsyncSessionLocal
        from agent_kanban.models import User
        from agent_kanban.auth import hash_password
        settings = get_settings()
        if not settings.bootstrap_admin_password:
            return  # UI /api/setup flow handles first-run
        async with AsyncSessionLocal() as session:
            count = (await session.execute(select(User))).scalars().all()
            if count:
                return
            session.add(User(
                username=settings.bootstrap_admin_username,
                password_hash=hash_password(settings.bootstrap_admin_password),
                is_admin=True,
            ))
            await session.commit()
```

- [ ] **Step 5: Run tests + commit**

Run: `uv run pytest -v`
Expected: all passing.

```bash
git add -A
git commit -m "feat(auth): /api/setup first-run + PATCH /api/users for password/admin"
```

---

## Task 4: CORS credentials + frontend updates

Enable `allow_credentials=True` (needed for cross-origin cookie deploys), update the frontend to use WS tickets + the new setup/edit flows.

**Files:**
- Modify: `src/agent_kanban/server.py` (CORS)
- Modify: `web/src/api.ts` (fetchWsTicket, setup, updateUser; WS uses ticket)
- Modify: `web/src/pages/Login.tsx` (real setup flow)
- Modify: `web/src/pages/Admin.tsx` (edit user form)

- [ ] **Step 1: Enable CORS credentials**

In `src/agent_kanban/server.py`, in the CORS middleware block, add `allow_credentials=True`:
```python
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
```

- [ ] **Step 2: Update `api.ts`**

Add to the `api` object:
```typescript
  async fetchWsTicket(): Promise<{ ticket: string; expires_in: number }> {
    return j(await fetch(`${BASE}/ws-ticket`, { method: "POST", credentials: "include" }));
  },
  async setup(username: string, password: string): Promise<void> {
    await fetch(`${BASE}/setup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ username, password }),
    });
  },
  async updateUser(
    id: number,
    patch: { current_password?: string; password?: string; is_admin?: boolean }
  ): Promise<{ id: number; username: string; is_admin: boolean }> {
    return j(await fetch(`${BASE}/users/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(patch),
    }));
  },
```

Update `subscribeWebSocket` to fetch a ticket before connecting (async):
```typescript
export async function subscribeWebSocket(
  taskId: number | null,
  onMessage: (evt: { type: string; [k: string]: unknown }) => void,
  options: WSOptions = {}
): Promise<WSSubscription> {
  const maxRetries = options.maxRetries ?? 5;
  const baseDelayMs = options.baseDelayMs ?? 500;
  const proto = location.protocol === "https:" ? "wss:" : "ws:";

  let retryCount = 0;
  let closedByCaller = false;
  let ws: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  async function open() {
    // Fetch a fresh single-use ticket each time we (re)connect.
    let qParts: string[] = [];
    if (taskId) qParts.push(`task_id=${taskId}`);
    try {
      const { ticket } = await api.fetchWsTicket();
      qParts.push(`ticket=${encodeURIComponent(ticket)}`);
    } catch {
      // Cookie-only fallback (same-origin). Continue without ticket.
    }
    const q = qParts.length ? `?${qParts.join("&")}` : "";
    const url = `${proto}//${location.host}/ws${q}`;
    ws = new WebSocket(url);
    ws.onopen = () => { retryCount = 0; };
    ws.onmessage = (e) => {
      try { onMessage(JSON.parse(e.data)); } catch (err) { console.error("kanban: bad WS message", err); }
    };
    ws.onerror = (err) => { console.error("kanban: WS error", err); };
    ws.onclose = () => {
      if (closedByCaller) return;
      if (retryCount >= maxRetries) {
        console.error(`kanban: WS giving up after ${maxRetries} retries`);
        return;
      }
      const delay = baseDelayMs * Math.pow(2, retryCount);
      retryCount += 1;
      reconnectTimer = setTimeout(open, delay);
    };
  }

  await open();

  return {
    close: () => {
      closedByCaller = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (ws) ws.close();
    },
  };
}
```

Note: `subscribeWebSocket` is now `async` (returns `Promise<WSSubscription>`). Update call sites in `Board.tsx` and `CardDetail.tsx` to `await` it. Since both use it inside a `useEffect`, the pattern becomes:
```typescript
useEffect(() => {
  let sub: WSSubscription | null = null;
  let cancelled = false;
  refresh();
  subscribeWebSocket(null, () => refresh()).then((s) => {
    if (cancelled) { s.close(); } else { sub = s; }
  });
  return () => { cancelled = true; sub?.close(); };
}, []);
```
Apply this pattern to both Board.tsx and CardDetail.tsx (CardDetail uses `taskId` instead of `null`).

- [ ] **Step 3: Update `Login.tsx` with the real setup flow**

Replace the setup-mode branch in `submit()`:
```typescript
  async function submit() {
    setError(null);
    try {
      if (mode === "setup") {
        if (password.length < 8) {
          setError("password must be at least 8 characters");
          return;
        }
        await api.setup(username || "admin", password);
        // After setup, log in with the new creds.
        await api.login(username || "admin", password);
        onLoggedIn();
        return;
      }
      await api.login(username, password);
      onLoggedIn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "login failed");
    }
  }
```
Add a `confirm` password input shown only in setup mode (and validate match) for a better UX. Update the button label to "Set up" in setup mode.

- [ ] **Step 4: Update `Admin.tsx` with an edit-user form**

Add a small inline edit form per user row (or a modal). Minimum: a "Change password" button that prompts for current + new password, and an "admin" toggle checkbox. Use `api.updateUser`. This is intentionally minimal — a full user-management UX is out of scope.

- [ ] **Step 5: Verify the build + commit**

Run: `cd web && pnpm build`
Expected: clean.

```bash
git add -A
git commit -m "feat(web): WS ticket flow, /api/setup login, CORS credentials, user edit"
```

---

## Task 5: Spec + README updates

**Files:**
- Modify: `docs/superpowers/specs/2026-07-05-agent-kanban-design.md` (§5.3 rewrite, add §5.4/§5.5)
- Modify: `README.md` (already mostly done in Phase 4; add ticket + setup notes)

- [ ] **Step 1: Rewrite spec §5.3 and add §5.4/§5.5**

Open `docs/superpowers/specs/2026-07-05-agent-kanban-design.md`. Find §5.3 (currently "Single-user, no auth..."). Replace it with:

```markdown
### 5.3 Authorization model (updated Phase 4)

The board supports two principal kinds:

- **Users** (humans): authenticate with username + password (bcrypt-hashed, cost 12). Sessions are signed HttpOnly cookies (`kanban_session`, SameSite=Lax, Secure when `PUBLIC_URL` is https).
- **Tokens** (agents): opaque bearer tokens (`secrets.token_urlsafe(32)`), bcrypt-hashed at rest, shown once at creation. Each token is bound to an `agent_name`.

Every REST route, the WebSocket, and every MCP tool requires a resolved `Principal`. Mutation MCP tools additionally verify that the `agent` argument equals the calling token's `agent_name`; mismatch raises `PermissionError` (surfaced as a tool error to the agent). Read MCP tools require any valid principal.

`SESSION_SECRET` (the cookie-signing key) is required in production: the docker-compose file fails loudly if unset, and the server refuses to start with a known-insecure default when `PUBLIC_URL` is https. First-run setup is via `POST /api/setup` (creates the first admin) when no users exist; the `AGENT_KANBAN_BOOTSTRAP_ADMIN_PASSWORD` env var is an alternative for headless automation.

### 5.4 WebSocket tickets

Browsers cannot set `Authorization` headers on WebSocket connections, so the bearer cannot flow as a header for cross-origin WS. The board issues single-use, 60-second WS tickets: `POST /api/ws-ticket` (cookie/bearer authed) → `{ticket, expires_in}`. The frontend connects the socket with `?ticket=<nonce>`. The nonce is consumed on use, so it never leaks the long-lived bearer into proxy/access logs. The session cookie remains the primary WS auth for same-origin deployments.

### 5.5 Token prefix index

Token lookup filters by the first 8 characters of the plaintext (`token_prefix`, indexed) before bcrypt-verifying, reducing the per-request cost from O(N) bcrypt checks to one index lookup + one bcrypt check. Legacy tokens (minted before Phase 5) have an empty prefix and fall back to a full scan.
```

- [ ] **Step 2: Update README**

In `README.md`, in the Authentication section, add a short note about first-run setup (`/api/setup` UI flow instead of stdout) and WS tickets. Update the "First run" subsection:

```markdown
### First run

On first startup with an empty database, the UI shows a setup screen: choose an admin username + password (8+ chars) and submit. Alternatively, set `AGENT_KANBAN_BOOTSTRAP_ADMIN_PASSWORD` to create the admin headlessly (for automation). After setup, log in and go to Admin → Tokens to mint tokens for your agents.
```

- [ ] **Step 3: Commit**

```bash
git add docs/ README.md
git commit -m "docs: update spec and README for auth (Phase 4+5)"
```

---

## Phase 5 Acceptance Criteria

- [ ] `uv run pytest -v` passes (90 prior + new tests).
- [ ] `cd web && pnpm build` succeeds.
- [ ] `uv run ruff check src/ tests/` is clean.
- [ ] `GET /api/progress/last` and other protected routes still require auth (no regression).
- [ ] `Token.token_prefix` column exists; `_resolve_bearer` filters by prefix; round-trip migration clean.
- [ ] `POST /api/ws-ticket` returns a single-use nonce; WS accepts `?ticket=`; the nonce is consumed on use.
- [ ] `POST /api/setup` creates the first admin when `needs_setup`; 409 otherwise.
- [ ] `PATCH /api/users/{id}` changes password (requires `current_password`) and toggles `is_admin` (guards last admin).
- [ ] CORS `allow_credentials=True`.
- [ ] Login page has a real setup flow (no "read stdout" advisory).
- [ ] Admin page can edit users (password + admin toggle).
- [ ] Spec §5.3 rewritten; §5.4 and §5.5 added; README first-run updated.

---

## Notes for the implementer

- **Migration `0003_phase5.py`** adds `token_prefix` with `server_default=""` so existing rows (from Phase 4 tests) don't break. New mints populate it. The full-scan fallback covers legacy rows in prod.
- **WS ticket store is in-memory.** Phase 5 is single-process (one uvicorn worker). If we ever run multiple workers, move tickets to Redis with the same mint/resolve semantics.
- **`subscribeWebSocket` is now async.** Both Board and CardDetail `useEffect` hooks must handle the promise correctly (guard against unmount-before-resolve with a `cancelled` flag, close the sub in cleanup).
- **`/api/setup` password min length 8.** Enforced server-side; mirror in the UI.
- **PATCH user password requires the acting admin's current password**, not the target's. This is a deliberate choice: an admin can reset any user's password but must re-prove their own identity. Document this.
- **CORS `allow_credentials=True` + wildcard origin is invalid** per the spec. The default `cors_origins` is explicit (`["http://localhost:5173"]`), so this is safe; prod must set the real origin.
- **The `?token=` WS param is kept as a deprecated fallback** for one release so existing agents/scripts don't break. Remove it in Phase 6.
