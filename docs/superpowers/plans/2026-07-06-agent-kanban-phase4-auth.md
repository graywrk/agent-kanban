# Agent Kanban — Phase 4 Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add real authentication to a publicly-deployed board: passwords for humans (login → signed cookie session), tokens for agents (Bearer header), a UI admin panel to manage both, and enforce the `agent` parameter against the token's identity on every MCP mutation.

**Architecture:** A new `auth` module owns token/user models, password hashing (bcrypt), token verification, and FastAPI dependencies (`get_current_principal`) that return a `Principal` (either a `User` row or a `Token` row). Every REST route, the WebSocket, and the MCP server take a `Principal` dependency; the MCP layer additionally checks that the `agent` argument matches the token's `agent_name` (or is `user` for human-session principals). The frontend gains a login page, a token-management admin page, and a bearer-token-in-localStorage path for `fetch`/WebSocket.

**Tech Stack:** Python 3.11 + FastAPI + sqlmodel + alembic (existing); `bcrypt>=4.2` (new dep for password hashing); `itsdangerous>=2.2` (new dep for signed session cookies — already a Starlette transitive dep, but pin explicitly); React/Vite/TS for the UI.

**Spec:** Extends `docs/superpowers/specs/2026-07-05-agent-kanban-design.md` §5.3 (authorization model). The spec's "single-user, no auth" is upgraded to multi-user with auth per user decision (2026-07-06). All other spec sections (data model, MCP tools, UI layout) are preserved.

## Global Constraints

- All Phase 1–3 constraints still apply (Python 3.11+, PostgreSQL on host port **5436**, MCP SDK `mcp>=1.27,<2.0`, default port 7331).
- **DB migrations ARE required** — new tables `users` and `tokens`. Generated via `alembic revision --autogenerate`.
- **New deps:** `bcrypt>=4.2` (password hashing), `itsdangerous>=2.2` (signed session cookies — pin even though transitive).
- **The MCP tool contract is preserved** — the `agent` parameter stays on all mutation tools. New rule: `agent` MUST equal the calling token's `agent_name`, or `user` for human-session principals. Mismatch → 403.
- **Backward compat:** an existing agent configured with a token works without code changes. An agent configured WITHOUT a token stops working (401) — this is the intended security upgrade.
- Tokens are **opaque random strings** (32 bytes, base64). Stored as **bcrypt hashes** in the DB (never plaintext). The full token is shown ONCE at creation, never again.
- Passwords hashed with bcrypt cost 12.
- Session cookie name `kanban_session`, `HttpOnly`, `SameSite=Lax`, `Secure` when `settings.public_url` is https.
- The board is assumed **publicly reachable** — every endpoint except `/api/login`, `/api/setup-status`, `/mcp` (which does its own bearer auth), and the static SPA mount requires a principal.

---

## File Structure

```
src/agent_kanban/
├── auth.py              # CREATE: User/Token models (sqlmodel), hashing, Principal type, deps
├── models.py            # (unchanged — User/Token live in auth.py to keep the auth domain together)
├── routes/
│   ├── auth.py          # CREATE: POST /api/login, POST /api/logout, GET /api/me,
│   │                    #        GET /api/setup-status, GET/POST/DELETE /api/tokens,
│   │                    #        POST /api/users, GET/DELETE /api/users
│   └── *.py             # MODIFY: every handler gains a `principal: Principal = Depends(get_current_principal)` arg
├── mcp_server.py        # MODIFY: tools take principal dep; verify agent == principal.agent_name
├── server.py            # MODIFY: register auth router; add SessionMiddleware; add bootstrap on startup
├── services.py          # MODIFY: post_comment_with_status etc. unchanged; auth lives at route layer
├── config.py            # MODIFY: add session_secret, bootstrap_admin_password (optional env)
├── cli.py               # MODIFY: add `kanban reset-admin` subcommand for recovery
migrations/versions/
└── 0002_auth.py         # CREATE: users + tokens tables
tests/
├── test_auth.py         # CREATE: hashing, token verify, principal resolution
└── test_routes_auth.py  # CREATE: login/logout, token CRUD, 401 on missing creds, agent-mismatch 403
web/src/
├── api.ts               # MODIFY: attach session cookie / bearer; 401 → redirect to login
├── pages/
│   ├── Login.tsx        # CREATE
│   └── Admin.tsx        # CREATE: token + user management
├── components/
│   └── ...              # (existing, minor: header gets logout + admin link)
└── App.tsx              # MODIFY: route between Login/Board/Admin based on /api/me
```

**Decomposition rationale:** Task 1 (models + migration) is the data foundation. Task 2 (auth module: hashing, deps) is the verification core. Task 3 (auth routes: login, tokens CRUD) is the human-facing surface. Task 4 (enforce principal on REST + WS) closes the REST security hole. Task 5 (MCP agent-param enforcement) closes the agent-param-spoofing hole. Task 6 (bootstrap admin) makes first-run workable. Task 7 (frontend login + admin) makes it usable. Each task ends green and committable.

---

## Task 1: User and Token models + migration

**Files:**
- Modify: `src/agent_kanban/models.py` (add `User`, `Token` models)
- Create: `migrations/versions/0002_auth.py` (via autogenerate)

**Interfaces:**
- Produces: `User(id, username, password_hash, is_admin, created_at)` and `Token(id, agent_name, token_hash, created_by_user_id, created_at, last_used_at, description)` sqlmodel classes on the existing metadata.

- [ ] **Step 1: Add the models**

Open `src/agent_kanban/models.py`. After the existing `Artifact` class, append:
```python
class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    password_hash: str
    is_admin: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))


class Token(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    agent_name: str = Field(index=True)
    token_hash: str  # bcrypt hash of the opaque token
    description: Optional[str] = None
    created_by_user_id: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
    last_used_at: Optional[datetime] = None
```

- [ ] **Step 2: Generate the migration**

Run:
```bash
uv run alembic revision --autogenerate -m "auth: users and tokens tables"
```
Rename the generated file to `0002_auth.py`.

Open `0002_auth.py`. Verify it creates `user` and `token` tables with the columns above. If autogenerate emitted `sa.Boolean()` for `is_admin` without a server_default, add `server_default=sa.text("false")` to the column so existing rows (none yet) and future inserts behave. Similarly `last_used_at` should be `nullable=True`.

- [ ] **Step 3: Test the round-trip**

```bash
docker exec ak-pg psql -U kanban -d postgres -c "DROP DATABASE IF EXISTS kanban;"
docker exec ak-pg psql -U kanban -d postgres -c "CREATE DATABASE kanban OWNER kanban;"
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```
Expected: all three succeed (the new tables come and go cleanly).

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -q`
Expected: 71 passing (no regression — tests don't use the new tables yet).

- [ ] **Step 5: Commit**

```bash
git add src/agent_kanban/models.py migrations/versions/0002_auth.py
git commit -m "feat(models): User and Token tables for auth"
```

---

## Task 2: auth module — hashing, Principal, dependencies

**Files:**
- Create: `src/agent_kanban/auth.py`
- Create: `tests/test_auth.py`
- Modify: `pyproject.toml` (add `bcrypt>=4.2`, `itsdangerous>=2.2`)

**Interfaces:**
- Produces:
  - `hash_password(plain: str) -> str` and `verify_password(plain, hashed) -> bool` — bcrypt cost 12.
  - `hash_token(plain: str) -> str` and `verify_token(plain, hashed) -> bool` — bcrypt cost 12 (token hashed same way; the plaintext token is the "password").
  - `generate_token() -> str` — `secrets.token_urlsafe(32)` (43-char urlsafe string).
  - `Principal` — a small dataclass/Pydantic model: `kind: Literal["user", "token"]`, `user_id: Optional[int]`, `agent_name: Optional[str]`, `is_admin: bool`. For a user principal, `agent_name="user"`. For a token principal, `agent_name` is the token's `agent_name`.
  - `async def get_current_principal(request: Request, session) -> Principal` — FastAPI dependency. Resolves from (in order): (a) session cookie → User row; (b) `Authorization: Bearer <token>` header → Token row (hash-verified). Raises `HTTPException(401)` if neither resolves.

- [ ] **Step 1: Add dependencies**

In `pyproject.toml` `[project] dependencies`, add:
```toml
    "bcrypt>=4.2",
    "itsdangerous>=2.2",
```
Run: `uv sync --extra dev`

- [ ] **Step 2: Write failing tests**

Create `tests/test_auth.py`:
```python
import pytest

from agent_kanban.auth import (
    generate_token,
    hash_password,
    hash_token,
    verify_password,
    verify_token,
)


def test_hash_and_verify_password_roundtrip():
    h = hash_password("hunter2")
    assert h != "hunter2"
    assert verify_password("hunter2", h) is True
    assert verify_password("wrong", h) is False


def test_hash_and_verify_token_roundtrip():
    plain = generate_token()
    assert len(plain) >= 32
    h = hash_token(plain)
    assert h != plain
    assert verify_token(plain, h) is True
    assert verify_token("not-the-token", h) is False


def test_password_hashes_are_salted():
    """Same plaintext → different hashes (bcrypt salts)."""
    h1 = hash_password("same")
    h2 = hash_password("same")
    assert h1 != h2
    assert verify_password("same", h1) and verify_password("same", h2)


def test_generate_token_unique():
    tokens = {generate_token() for _ in range(1000)}
    assert len(tokens) == 1000
```

- [ ] **Step 3: Run, verify fail**

Run: `uv run pytest tests/test_auth.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Implement `auth.py`**

Create `src/agent_kanban/auth.py`:
```python
"""Authentication: password hashing, token generation/verification, Principal resolution."""
import secrets
from typing import Literal, Optional

import bcrypt
from fastapi import HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from agent_kanban.models import Token, User

_BCRYPT_COST = 12


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(_BCRYPT_COST)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def hash_token(plain: str) -> str:
    return hash_password(plain)


def verify_token(plain: str, hashed: str) -> bool:
    return verify_password(plain, hashed)


def generate_token() -> str:
    return secrets.token_urlsafe(32)


class Principal(BaseModel):
    kind: Literal["user", "token"]
    user_id: Optional[int] = None
    agent_name: str  # "user" for human sessions, else the token's agent_name
    is_admin: bool = False

    @property
    def is_token(self) -> bool:
        return self.kind == "token"

    @property
    def is_user(self) -> bool:
        return self.kind == "user"


async def _resolve_bearer(session: AsyncSession, header_value: str) -> Optional[Principal]:
    """Look up a Token row whose hash matches the bearer value.

    Tokens are hashed with bcrypt; we don't know the salt ahead of time, so we
    scan candidate rows. For a small N of tokens (typical: <50) this is fine.
    If N grows, add a token_prefix column (first 8 chars) and index it, then
    filter on the prefix before the bcrypt loop.
    """
    result = await session.execute(select(Token))
    for row in result.scalars():
        if verify_token(header_value, row.token_hash):
            row.last_used_at = None  # set by the caller after commit if desired
            return Principal(
                kind="token",
                agent_name=row.agent_name,
                is_admin=False,
            )
    return None


async def _resolve_cookie(session: AsyncSession, user_id: int) -> Optional[Principal]:
    user = await session.get(User, user_id)
    if user is None:
        return None
    return Principal(kind="user", user_id=user.id, agent_name="user", is_admin=user.is_admin)


async def get_current_principal(request: Request) -> Principal:
    """FastAPI dependency. Resolves a Principal from session cookie or bearer header.

    Raises 401 if neither resolves. Attach to every protected route.
    """
    session_gen = _get_request_session(request)
    session: AsyncSession = await session_gen.__anext__()  # type: ignore[attr-defined]
    try:
        # 1. Session cookie → user.
        user_id = request.session.get("user_id") if hasattr(request, "session") else None
        if user_id is not None:
            p = await _resolve_cookie(session, int(user_id))
            if p is not None:
                return p
        # 2. Bearer header → token.
        authz = request.headers.get("authorization", "")
        if authz.lower().startswith("bearer "):
            token_value = authz[7:].strip()
            p = await _resolve_bearer(session, token_value)
            if p is not None:
                return p
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    finally:
        await session_gen.aclose()  # type: ignore[attr-defined]


async def _get_request_session(request: Request):
    """Yield an AsyncSession scoped to this request, used by get_current_principal."""
    from agent_kanban.db import AsyncSessionLocal
    async with AsyncSessionLocal() as s:
        yield s
```

> **Note for the implementer:** `request.session` requires Starlette's `SessionMiddleware` to be installed (Task 4 mounts it). The `hasattr(request, "session")` guard keeps resolution working in tests that don't mount the middleware, but Task 4's tests WILL mount it via `create_app()`. The double session allocation (one in `get_current_principal`, one via the route's `get_session` dep) is fine — asyncpg pools cheaply and SQLAlchemy handles independent sessions correctly.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_auth.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/agent_kanban/auth.py tests/test_auth.py
git commit -m "feat(auth): bcrypt hashing, token generation, Principal resolution"
```

---

## Task 3: Auth REST routes — login, logout, me, tokens CRUD, users CRUD

**Files:**
- Create: `src/agent_kanban/routes/auth.py`
- Create: `tests/test_routes_auth.py`
- Modify: `src/agent_kanban/server.py` (mount SessionMiddleware + auth router — done in Task 4, but the auth router itself is testable via TestClient with the middleware)

**Interfaces:**
- Produces REST endpoints:
  - `GET /api/setup-status` — `{needs_setup: bool}`. True if no users exist (first run).
  - `POST /api/login` — body `{username, password}`. 200 + sets `kanban_session` cookie; 401 on bad creds.
  - `POST /api/logout` — clears the session cookie. Always 200.
  - `GET /api/me` — returns the current `Principal` (or 401).
  - `GET /api/tokens` — list tokens (admin only). Returns `[{id, agent_name, description, created_at, last_used_at}]` (NEVER the hash).
  - `POST /api/tokens` — body `{agent_name, description?}`. Creates a token, returns `{id, agent_name, description, token: "<plaintext-once>"}`. Admin only.
  - `DELETE /api/tokens/{id}` — revoke. Admin only.
  - `POST /api/users` — body `{username, password, is_admin?}`. Admin only.
  - `GET /api/users` — list. Admin only.
  - `DELETE /api/users/{id}` — admin only; cannot delete the last admin.

- [ ] **Step 1: Write failing tests**

Create `tests/test_routes_auth.py`:
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
    # /api/tasks now requires a principal (Task 4 enforces this; this test
    # exists in Task 3 to document the contract early but will only pass
    # after Task 4 wires the dep. Skip-style: expect 401 OR 200 — Task 4
    # tightens to 401. For now, just verify the endpoint exists.)
    r = await client.get("/api/tasks")
    # Before Task 4: 200. After Task 4: 401. We assert 401 once Task 4 lands.
    assert r.status_code in (200, 401)
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_routes_auth.py -v`
Expected: FAIL — no `/api/login` etc.

- [ ] **Step 3: Implement `routes/auth.py`**

Create `src/agent_kanban/routes/auth.py`:
```python
"""Auth REST routes: setup-status, login, logout, me, tokens CRUD, users CRUD."""
from datetime import UTC, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from agent_kanban.auth import (
    Principal,
    generate_token,
    get_current_principal,
    hash_password,
    hash_token,
    verify_password,
)
from agent_kanban.db import get_session
from agent_kanban.models import Token, User

router = APIRouter(prefix="/api", tags=["auth"])


def _require_admin(p: Principal) -> None:
    if not p.is_admin:
        raise HTTPException(403, "admin required")


# ---- Setup status (public) ----
@router.get("/setup-status")
async def setup_status(session: AsyncSession = Depends(get_session)):
    count = (await session.execute(select(func.count(User.id)))).scalar_one()
    return {"needs_setup": count == 0}


# ---- Login / logout (login is public) ----
class LoginBody(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(body: LoginBody, request: Request, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(User).where(User.username == body.username))
    user = result.scalars().first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "invalid credentials")
    request.session["user_id"] = str(user.id)
    return {"username": user.username, "is_admin": user.is_admin}


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me")
async def me(principal: Principal = Depends(get_current_principal)):
    return principal


# ---- Tokens (admin) ----
class TokenCreate(BaseModel):
    agent_name: str
    description: Optional[str] = None


@router.get("/tokens")
async def list_tokens(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
):
    _require_admin(principal)
    result = await session.execute(select(Token).order_by(Token.created_at.desc()))
    return [
        {
            "id": t.id,
            "agent_name": t.agent_name,
            "description": t.description,
            "created_at": t.created_at.isoformat() + "Z",
            "last_used_at": (t.last_used_at.isoformat() + "Z") if t.last_used_at else None,
        }
        for t in result.scalars()
    ]


@router.post("/tokens", status_code=201)
async def create_token(
    body: TokenCreate,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
):
    _require_admin(principal)
    plain = generate_token()
    tok = Token(
        agent_name=body.agent_name,
        token_hash=hash_token(plain),
        description=body.description,
        created_by_user_id=principal.user_id,
    )
    session.add(tok)
    await session.commit()
    await session.refresh(tok)
    return {
        "id": tok.id,
        "agent_name": tok.agent_name,
        "description": tok.description,
        "token": plain,  # plaintext, shown once
    }


@router.delete("/tokens/{token_id}")
async def delete_token(
    token_id: int,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
):
    _require_admin(principal)
    tok = await session.get(Token, token_id)
    if tok is None:
        raise HTTPException(404, "token not found")
    await session.delete(tok)
    await session.commit()
    return {"ok": True}


# ---- Users (admin) ----
class UserCreate(BaseModel):
    username: str
    password: str
    is_admin: bool = False


@router.get("/users")
async def list_users(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
):
    _require_admin(principal)
    result = await session.execute(select(User).order_by(User.created_at))
    return [
        {
            "id": u.id,
            "username": u.username,
            "is_admin": u.is_admin,
            "created_at": u.created_at.isoformat() + "Z",
        }
        for u in result.scalars()
    ]


@router.post("/users", status_code=201)
async def create_user(
    body: UserCreate,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
):
    _require_admin(principal)
    existing = (
        await session.execute(select(User).where(User.username == body.username))
    ).scalars().first()
    if existing is not None:
        raise HTTPException(409, "username exists")
    u = User(username=body.username, password_hash=hash_password(body.password), is_admin=body.is_admin)
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return {"id": u.id, "username": u.username, "is_admin": u.is_admin}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
):
    _require_admin(principal)
    if user_id == principal.user_id:
        raise HTTPException(400, "cannot delete yourself")
    admin_count = (await session.execute(select(func.count(User.id)).where(User.is_admin == True))).scalar_one()  # noqa: E712
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(404, "user not found")
    if target.is_admin and admin_count <= 1:
        raise HTTPException(400, "cannot delete the last admin")
    await session.delete(target)
    await session.commit()
    return {"ok": True}
```

- [ ] **Step 4: Mount SessionMiddleware + auth router in `server.py`**

Open `src/agent_kanban/server.py`. Two changes:

a) Add imports:
```python
from starlette.middleware.sessions import SessionMiddleware
from agent_kanban.config import get_settings
from agent_kanban.routes import auth as auth_routes
```
(`get_settings` is already imported; just ensure `auth_routes` is imported.)

b) In `create_app()`, AFTER the CORS middleware, add the session middleware:
```python
    settings = get_settings()
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        session_cookie="kanban_session",
        same_site="lax",
        https_only=settings.public_url.startswith("https"),
    )
    app.include_router(auth_routes.router)
```

And in `config.py`, add two settings:
```python
    session_secret: str = "dev-insecure-secret-change-me"  # override via env in prod
    public_url: str = "http://localhost:7331"
    bootstrap_admin_username: str = "admin"
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_routes_auth.py -v`
Expected: PASS (7 tests). The last test (`test_protected_route_401_without_creds`) accepts 200 OR 401 — Task 4 will tighten it.

- [ ] **Step 6: Run full suite**

Run: `uv run pytest -q`
Expected: 71 prior + 4 auth-hash + 7 routes-auth = 82 passing.

- [ ] **Step 7: Commit**

```bash
git add src/agent_kanban/routes/auth.py src/agent_kanban/server.py src/agent_kanban/config.py tests/test_routes_auth.py
git commit -m "feat(auth): login/logout/me, tokens CRUD, users CRUD, session middleware"
```

---

## Task 4: Enforce Principal on all REST routes + WebSocket

**Files:**
- Modify: every file in `src/agent_kanban/routes/` EXCEPT `auth.py` (add `principal: Principal = Depends(get_current_principal)` to handlers)
- Modify: `src/agent_kanban/routes/ws.py`
- Modify: `tests/test_routes_auth.py` (tighten the last test to expect 401)

**Interfaces:**
- Produces: every `/api/*` route (except `/api/login`, `/api/setup-status`, `/api/logout` which are public or self-authenticating) requires a resolved Principal. The WebSocket reads the session cookie OR a `?token=<bearer>` query param.

- [ ] **Step 1: Tighten the contract test**

In `tests/test_routes_auth.py`, change the last test to:
```python
@pytest.mark.asyncio
async def test_protected_route_401_without_creds(client):
    r = await client.get("/api/tasks")
    assert r.status_code == 401
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_routes_auth.py::test_protected_route_401_without_creds -v`
Expected: FAIL (200, not 401 — the route has no principal dep yet).

- [ ] **Step 3: Add `principal` dep to every protected handler**

For each file in `src/agent_kanban/routes/` except `auth.py`:
- `tasks.py` — `get_tasks`, `post_task`, `get_one`, `patch_task`
- `projects.py` — `list_projects`, `create_project`, `get_project`
- `progress.py` — `list_progress`, `last_progress_timestamps`
- `comments.py` — `get_comments`, `add_comment`
- `artifacts.py` — `get_artifact_content`

Add to each handler signature:
```python
    principal: Principal = Depends(get_current_principal),
```
And add the import at the top of each file:
```python
from agent_kanban.auth import Principal, get_current_principal
```

The `principal` parameter is unused in the body for most routes (they just need the gate) — that's fine. Where you want to know who acted (e.g. `comments.add_comment` could use `principal.agent_name` for authorship), use it; otherwise it's a pure auth gate.

> **Important:** existing route tests (`test_routes_tasks.py`, etc.) will now FAIL with 401 because they don't authenticate. The cleanest fix is to add a pytest fixture that creates an admin user + logs in, yielding a client with a valid session cookie. Add this to `tests/conftest.py`:
```python
@pytest_asyncio.fixture
async def authed_client(db_url):
    """An httpx AsyncClient with a logged-in admin session."""
    from agent_kanban.config import get_settings
    get_settings.cache_clear()
    from agent_kanban.server import create_app
    from agent_kanban.db import AsyncSessionLocal
    from agent_kanban.models import User
    from agent_kanban.auth import hash_password
    async with AsyncSessionLocal() as session:
        session.add(User(username="admin", password_hash=hash_password("pw"), is_admin=True))
        await session.commit()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await c.post("/api/login", json={"username": "admin", "password": "pw"})
        yield c
```
Then update each existing route test to use `authed_client` instead of the bare `client` fixture. The fixture name is `authed_client` — find/replace `client` → `authed_client` in `test_routes_tasks.py`, `test_routes_progress.py`, `test_routes_comments.py`, `test_routes_artifacts.py`, `test_e2e_smoke.py`.

For `test_e2e_smoke.py`, the MCP `call_tool` calls also need a principal — Task 5 handles that. For now, the e2e test will break on the MCP step; mark it `pytest.skip` with a note "re-enabled in Task 5" and un-skip in Task 5.

- [ ] **Step 4: Update the WebSocket to require auth**

Open `src/agent_kanban/routes/ws.py`. Add a `token: Optional[str] = None` query param and resolve a principal before accepting. Replace the file with:
```python
"""WebSocket endpoint for live updates."""
from contextlib import suppress
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from agent_kanban.auth import _resolve_bearer, _resolve_cookie
from agent_kanban.db import AsyncSessionLocal
from agent_kanban.events import event_bus

router = APIRouter(tags=["ws"])


async def _ws_principal(websocket: WebSocket, token: Optional[str]) -> bool:
    """Return True if the websocket carries a valid session cookie or bearer token."""
    async with AsyncSessionLocal() as session:
        # Session cookie first.
        user_id = websocket.session.get("user_id") if hasattr(websocket, "session") else None
        if user_id is not None:
            p = await _resolve_cookie(session, int(user_id))
            if p is not None:
                return True
        if token:
            p = await _resolve_bearer(session, token)
            if p is not None:
                return True
    return False


@router.websocket("/ws")
async def ws_endpoint(
    websocket: WebSocket,
    task_id: Optional[int] = None,
    token: Optional[str] = Query(None),
):
    ok = await _ws_principal(websocket, token)
    if not ok:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()
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

- [ ] **Step 5: Update WS tests to authenticate**

In `tests/test_ws.py`, the `TestClient` blocks must login before connecting. Add a helper that creates the admin user + logs in, then connect the WS with the session cookie (TestClient persists cookies). If TestClient's websocket_connect doesn't carry cookies by default, pass the token via `?token=<bearer>` — create a token via the API first and use it.

Concretely, update both WS tests to do:
```python
    # Login first.
    from agent_kanban.db import AsyncSessionLocal
    from agent_kanban.models import User
    from agent_kanban.auth import hash_password
    async with AsyncSessionLocal() as session:
        session.add(User(username="admin", password_hash=hash_password("pw"), is_admin=True))
        await session.commit()
    client.post("/api/login", json={"username": "admin", "password": "pw"})
    # Now the TestClient has the session cookie; websocket_connect carries it.
```

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -v`
Expected: all passing. The e2e test is skipped (Task 5 re-enables it). Existing route tests pass because they now use `authed_client`.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(auth): enforce Principal on all REST routes and WebSocket"
```

---

## Task 5: MCP agent-parameter enforcement + bootstrap admin

**Files:**
- Modify: `src/agent_kanban/mcp_server.py` (every tool resolves a Principal from the request context; verify `agent` matches)
- Modify: `src/agent_kanban/server.py` (add bootstrap-on-startup hook)
- Modify: `tests/test_mcp_server.py`
- Modify: `tests/test_e2e_smoke.py` (un-skip, authenticate via a token)

**Interfaces:**
- Produces: every MCP tool receives a `Principal` resolved from the underlying ASGI request's `Authorization: Bearer` header. The tool verifies that the `agent` argument equals `principal.agent_name` (tokens) or `"user"` (human sessions), raising 403 on mismatch. The board auto-creates an `admin` user on startup if no users exist, with a password read from `settings.bootstrap_admin_password` (env: `AGENT_KANBAN_BOOTSTRAP_ADMIN_PASSWORD`) or printed to stdout once.

- [ ] **Step 1: Add the bootstrap hook**

Open `src/agent_kanban/server.py`. In `_lifespan`, before `yield`, add the bootstrap:
```python
    async def _bootstrap_admin():
        from sqlmodel import select
        from agent_kanban.db import AsyncSessionLocal
        from agent_kanban.models import User
        from agent_kanban.auth import hash_password
        import secrets as _secrets
        async with AsyncSessionLocal() as session:
            count = (await session.execute(select(User))).scalars().all()
            if count:
                return
            pw = get_settings().bootstrap_admin_password or _secrets.token_urlsafe(12)
            session.add(User(username=get_settings().bootstrap_admin_username, password_hash=hash_password(pw), is_admin=True))
            await session.commit()
            # Print once so the operator can grab it.
            print(f"\n[agent-kanban] Bootstrapped admin user '{get_settings().bootstrap_admin_username}' with password: {pw}\n", flush=True)

    await _bootstrap_admin()
```
Add `bootstrap_admin_password: str = ""` to `config.py` Settings.

- [ ] **Step 2: Resolve Principal inside MCP tools**

The MCP FastMCP framework doesn't expose the ASGI request directly to tool functions. The cleanest approach: read the `Authorization` header from a contextvar set by a small middleware on the mounted `/mcp` app.

In `src/agent_kanban/mcp_server.py`, add at module top:
```python
import contextvars
_mcp_principal: contextvars.ContextVar = contextvars.ContextVar("_mcp_principal")
```

Add a helper to resolve+set it per call:
```python
async def _resolve_mcp_principal(request) -> "Principal | None":
    """Read the Authorization header, return a Principal or None."""
    from agent_kanban.auth import _resolve_bearer
    from agent_kanban.db import AsyncSessionLocal
    authz = request.headers.get("authorization", "")
    if not authz.lower().startswith("bearer "):
        return None
    token_value = authz[7:].strip()
    async with AsyncSessionLocal() as session:
        return await _resolve_bearer(session, token_value)
```

The FastMCP streamable HTTP transport in the pinned SDK version (`mcp>=1.27,<2.0`) accepts a `request_factory` or runs tools with the Starlette request available via `mcp.server.fastmcp.context`. Concretely, in the SDK, tool functions can access the current request via:
```python
from mcp.server.fastmcp.context import get_http_request
```
Use this inside each tool to fetch the request, resolve the principal, and verify `agent`. If `get_http_request` is not available in your pinned version, fall back to a Starlette middleware on the mounted app that sets the contextvar.

Implement a verifier used at the top of every mutation tool:
```python
async def _require_matching_agent(agent: str) -> Principal:
    """Resolve the MCP principal and verify the agent arg matches."""
    from mcp.server.fastmcp.context import get_http_request
    request = get_http_request()
    principal = await _resolve_mcp_principal(request)
    if principal is None:
        raise PermissionError("authentication required (Bearer token)")
    if agent != principal.agent_name:
        raise PermissionError(
            f"agent {agent!r} does not match the authenticated token's agent_name {principal.agent_name!r}"
        )
    return principal
```

For READ tools (`get_next_task`, `list_tasks`, `get_comments`), require authentication but NOT a matching agent (any authenticated principal can read). Use:
```python
async def _require_any_principal() -> Principal:
    from mcp.server.fastmcp.context import get_http_request
    request = get_http_request()
    principal = await _resolve_mcp_principal(request)
    if principal is None:
        raise PermissionError("authentication required (Bearer token)")
    return principal
```

Then at the top of each tool body, call the right verifier. For example `claim_task` becomes:
```python
@mcp.tool()
async def claim_task(task_id: int, agent: str) -> dict:
    await _require_matching_agent(agent)
    async with AsyncSessionLocal() as session:
        result = await svc_claim_task(session, task_id, agent)
        return {"ok": result.ok, "reason": result.reason, "task": _task_to_dict(result.task) if result.task else None}
```

Apply `_require_matching_agent(agent)` to: `claim_task`, `post_progress`, `complete_task`, `request_review`, `post_comment`, `post_artifact`, `set_task_branch`, `set_task_pr`.
Apply `_require_any_principal()` to: `get_next_task`, `list_tasks`, `get_comments`.

> **Note for the implementer:** verify `from mcp.server.fastmcp.context import get_http_request` resolves in your pinned `mcp` version. If the import path differs (the SDK moved things between 1.2 and 1.27), find the correct one by running `uv run python -c "import mcp.server.fastmcp.context as c; print(dir(c))"` and locate the request accessor. If no accessor exists in your version, the fallback is a Starlette middleware wrapping `mcp_http_app` that populates `_mcp_principal` from the Authorization header before the MCP handler runs — then tools read `_mcp_principal.get()` directly without `get_http_request`.

- [ ] **Step 3: Update MCP tests to pass a bearer token**

In `tests/test_mcp_server.py`, every test that calls a tool must now provide a token. The cleanest way: a fixture that creates a token via the DB and patches the request accessor to return a principal. But the most realistic test is via the HTTP endpoint with a real bearer header. Since `mcp.call_tool` is in-process and bypasses HTTP, tests should instead exercise the contract via the ASGI client + `/mcp/` HTTP transport.

If rewriting all tests to HTTP is too large, the pragmatic path: add a module-level test fixture that monkeypatches `_resolve_mcp_principal` to return a known `Principal(agent_name="codex")` for the duration of the test, then `mcp.call_tool` works as before. Add at the top of `test_mcp_server.py`:
```python
@pytest.fixture(autouse=True)
def _stub_mcp_principal(monkeypatch):
    """Stub the MCP principal resolver so in-process tool calls appear authenticated."""
    from agent_kanban import mcp_server
    from agent_kanban.auth import Principal

    async def _stub(request):
        return Principal(kind="token", agent_name="codex")

    # Patch the verifier helpers to skip the request lookup entirely.
    async def _matching(agent):
        if agent != "codex":
            from agent_kanban.auth import _resolve_bearer  # noqa
            raise PermissionError(f"agent {agent!r} != 'codex'")
        return Principal(kind="token", agent_name="codex")

    async def _any():
        return Principal(kind="token", agent_name="codex")

    monkeypatch.setattr(mcp_server, "_require_matching_agent", _matching)
    monkeypatch.setattr(mcp_server, "_require_any_principal", _any)
```
Then existing tests that used `agent="codex"` pass; tests that used `agent="hermes"` for authz-rejection still pass (the stub rejects non-`codex`). Verify the existing authz tests still pass.

- [ ] **Step 4: Un-skip and fix the e2e test**

Open `tests/test_e2e_smoke.py`. It currently uses `client` for REST + `mcp.call_tool` for MCP. Update it to:
- Use `authed_client` for REST.
- Before the MCP steps, create a token via `POST /api/tokens` (as the logged-in admin) with `agent_name="hermes"`, capture the plaintext token.
- Patch `_require_matching_agent`/`_require_any_principal` as in Step 3 to return `agent_name="hermes"` for the duration of the test (so `agent="hermes"` in the MCP calls is accepted).

Un-skip the test.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -v`
Expected: all passing including the un-skipped e2e test.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(auth): MCP agent-param enforcement + bootstrap admin on startup"
```

---

## Task 6: Frontend — login page, admin panel, bearer in localStorage

**Files:**
- Create: `web/src/pages/Login.tsx`
- Create: `web/src/pages/Admin.tsx`
- Modify: `web/src/api.ts` (attach credentials; 401 → route to login)
- Modify: `web/src/App.tsx` (route by `/api/me` state)
- Modify: `web/src/pages/Board.tsx` (header: logout, admin link)
- Modify: `web/src/pages/CardDetail.tsx` (same header treatment)

**Interfaces:**
- Produces: `/login` (username/password → cookie via `/api/login`), `/admin` (token + user CRUD, admin only), and the main app routes redirect to `/login` when `/api/me` returns 401. `fetch` uses `credentials: "include"` so the session cookie flows; WebSocket connects with `?token=` if a bearer is present in localStorage (optional — the cookie works for same-origin).

- [ ] **Step 1: Update `api.ts` for credentials + 401 handling**

In `web/src/api.ts`, change the `j()` helper and all `fetch` calls to include `credentials: "include"`. Add a 401 handler that dispatches a `navigate-to-login` event:
```typescript
const BASE = "/api";

async function j<T>(res: Response): Promise<T> {
  if (res.status === 401) {
    window.dispatchEvent(new CustomEvent("kanban:unauthorized"));
    throw new Error("unauthorized");
  }
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}
```
And update every `fetch(`${BASE}/...`, { ... })` call to include `credentials: "include" as RequestInit`. (httpx TestClient-equivalent: browsers need this for cookies cross-origin; same-origin defaults to include, but explicit is safer.)

Add auth-specific calls:
```typescript
  async login(username: string, password: string): Promise<{ username: string; is_admin: boolean }> {
    return j(await fetch(`${BASE}/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ username, password }),
    }));
  },
  async logout(): Promise<void> {
    await fetch(`${BASE}/logout`, { method: "POST", credentials: "include" });
  },
  async me(): Promise<{ kind: string; agent_name: string; is_admin: boolean }> {
    return j(await fetch(`${BASE}/me`, { credentials: "include" }));
  },
  async setupStatus(): Promise<{ needs_setup: boolean }> {
    return j(await fetch(`${BASE}/setup-status`, { credentials: "include" }));
  },
  async listTokens(): Promise<Array<{ id: number; agent_name: string; description: string | null; created_at: string; last_used_at: string | null }>> {
    return j(await fetch(`${BASE}/tokens`, { credentials: "include" }));
  },
  async createToken(agent_name: string, description?: string): Promise<{ id: number; agent_name: string; description: string | null; token: string }> {
    return j(await fetch(`${BASE}/tokens`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ agent_name, description }),
    }));
  },
  async deleteToken(id: number): Promise<void> {
    await fetch(`${BASE}/tokens/${id}`, { method: "DELETE", credentials: "include" });
  },
  async listUsers(): Promise<Array<{ id: number; username: string; is_admin: boolean; created_at: string }>> {
    return j(await fetch(`${BASE}/users`, { credentials: "include" }));
  },
  async createUser(username: string, password: string, is_admin: boolean): Promise<void> {
    await fetch(`${BASE}/users`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ username, password, is_admin }),
    });
  },
  async deleteUser(id: number): Promise<void> {
    await fetch(`${BASE}/users/${id}`, { method: "DELETE", credentials: "include" });
  },
```

- [ ] **Step 2: Create `Login.tsx`**

Create `web/src/pages/Login.tsx`:
```tsx
import { useEffect, useState } from "react";
import { api } from "../api";

export function Login({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [mode, setMode] = useState<"login" | "setup">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.setupStatus().then((s) => setMode(s.needs_setup ? "setup" : "login")).catch(() => setMode("login"));
  }, []);

  async function submit() {
    setError(null);
    try {
      if (mode === "setup") {
        if (password !== confirm) { setError("passwords do not match"); return; }
        // The bootstrap admin is auto-created on first startup. On setup, we
        // just log in with the provided creds (the operator set the bootstrap
        // password via env, OR the auto-generated one was printed to stdout).
        // For a true "set your own password on first run" flow, a /api/setup
        // endpoint would be needed — that's a follow-up. For now, setup mode
        // just instructs the user to check the server logs.
        setError("First-run: the admin password was printed to the server console on first startup. Use it to log in, then change it in Admin.");
        setMode("login");
        return;
      }
      await api.login(username, password);
      onLoggedIn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "login failed");
    }
  }

  return (
    <div style={{ maxWidth: 360, margin: "80px auto", padding: 24, border: "1px solid #ddd", borderRadius: 8 }}>
      <h2 style={{ marginTop: 0 }}>Agent Kanban</h2>
      <input placeholder="username" value={username} onChange={(e) => setUsername(e.target.value)} style={{ width: "100%", marginBottom: 8, boxSizing: "border-box" }} />
      <input type="password" placeholder="password" value={password} onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()} style={{ width: "100%", marginBottom: 8, boxSizing: "border-box" }} />
      <button onClick={submit} style={{ width: "100%" }}>Log in</button>
      {error && <div style={{ color: "#dc2626", fontSize: 12, marginTop: 8 }}>{error}</div>}
    </div>
  );
}
```

- [ ] **Step 3: Create `Admin.tsx`**

Create `web/src/pages/Admin.tsx`:
```tsx
import { useEffect, useState } from "react";
import { api } from "../api";

interface TokenRow { id: number; agent_name: string; description: string | null; created_at: string; last_used_at: string | null }
interface UserRow { id: number; username: string; is_admin: boolean; created_at: string }

export function Admin({ onBack }: { onBack: () => void }) {
  const [tokens, setTokens] = useState<TokenRow[]>([]);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [newTokenAgent, setNewTokenAgent] = useState("");
  const [newTokenDesc, setNewTokenDesc] = useState("");
  const [mintedToken, setMintedToken] = useState<string | null>(null);
  const [newUser, setNewUser] = useState({ username: "", password: "", is_admin: false });

  async function refresh() {
    setTokens(await api.listTokens());
    setUsers(await api.listUsers());
  }
  useEffect(() => { refresh(); }, []);

  async function mint() {
    if (!newTokenAgent.trim()) return;
    const t = await api.createToken(newTokenAgent, newTokenDesc || undefined);
    setMintedToken(t.token);
    setNewTokenAgent(""); setNewTokenDesc("");
    refresh();
  }
  async function revoke(id: number) {
    await api.deleteToken(id);
    refresh();
  }
  async function addUser() {
    if (!newUser.username || !newUser.password) return;
    await api.createUser(newUser.username, newUser.password, newUser.is_admin);
    setNewUser({ username: "", password: "", is_admin: false });
    refresh();
  }
  async function removeUser(id: number) {
    await api.deleteUser(id);
    refresh();
  }

  return (
    <div style={{ padding: 16, maxWidth: 900, margin: "0 auto" }}>
      <button onClick={onBack}>← Back to board</button>
      <h2>Admin</h2>

      <h3>Tokens (agents)</h3>
      {mintedToken && (
        <div style={{ background: "#ecfdf5", border: "1px solid #6ee7b7", padding: 12, borderRadius: 6, marginBottom: 12, fontFamily: "monospace", fontSize: 12, wordBreak: "break-all" }}>
          Copy this token now — it won't be shown again:<br />
          {mintedToken}
          <button onClick={() => setMintedToken(null)} style={{ marginLeft: 8 }}>dismiss</button>
        </div>
      )}
      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <input placeholder="agent_name (e.g. codex)" value={newTokenAgent} onChange={(e) => setNewTokenAgent(e.target.value)} />
        <input placeholder="description (optional)" value={newTokenDesc} onChange={(e) => setNewTokenDesc(e.target.value)} />
        <button onClick={mint}>Mint</button>
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead><tr><th align="left">agent</th><th align="left">description</th><th align="left">created</th><th align="left">last used</th><th></th></tr></thead>
        <tbody>
          {tokens.map((t) => (
            <tr key={t.id}>
              <td>{t.agent_name}</td><td>{t.description}</td>
              <td>{new Date(t.created_at).toLocaleString()}</td>
              <td>{t.last_used_at ? new Date(t.last_used_at).toLocaleString() : "never"}</td>
              <td><button onClick={() => revoke(t.id)}>revoke</button></td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 style={{ marginTop: 24 }}>Users</h3>
      <div style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "center" }}>
        <input placeholder="username" value={newUser.username} onChange={(e) => setNewUser({ ...newUser, username: e.target.value })} />
        <input type="password" placeholder="password" value={newUser.password} onChange={(e) => setNewUser({ ...newUser, password: e.target.value })} />
        <label><input type="checkbox" checked={newUser.is_admin} onChange={(e) => setNewUser({ ...newUser, is_admin: e.target.checked })} /> admin</label>
        <button onClick={addUser}>Add</button>
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead><tr><th align="left">username</th><th align="left">admin</th><th align="left">created</th><th></th></tr></thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id}>
              <td>{u.username}</td><td>{u.is_admin ? "✓" : ""}</td>
              <td>{new Date(u.created_at).toLocaleString()}</td>
              <td><button onClick={() => removeUser(u.id)}>delete</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 4: Route by `/api/me` in `App.tsx`**

Replace `web/src/App.tsx`:
```tsx
import { useEffect, useState } from "react";
import { api } from "./api";
import { Login } from "./pages/Login";
import { Admin } from "./pages/Admin";
import { Board } from "./pages/Board";
import { CardDetail } from "./pages/CardDetail";

type View = { name: "loading" } | { name: "login" } | { name: "board" } | { name: "admin" } | { name: "card"; taskId: number };

export default function App() {
  const [view, setView] = useState<View>({ name: "loading" });
  const [me, setMe] = useState<{ is_admin: boolean } | null>(null);

  async function recheck() {
    try {
      const m = await api.me();
      setMe(m);
      setView({ name: "board" });
    } catch {
      setMe(null);
      setView({ name: "login" });
    }
  }

  useEffect(() => {
    recheck();
    const onUnauthorized = () => { setMe(null); setView({ name: "login" }); };
    window.addEventListener("kanban:unauthorized", onUnauthorized);
    return () => window.removeEventListener("kanban:unauthorized", onUnauthorized);
  }, []);

  if (view.name === "loading") return <div style={{ padding: 40 }}>Loading…</div>;
  if (view.name === "login") return <Login onLoggedIn={recheck} />;
  if (view.name === "admin") return <Admin onBack={() => setView({ name: "board" })} />;
  if (view.name === "card") return <CardDetail taskId={view.taskId} onBack={() => setView({ name: "board" })} />;

  // Board — add header buttons for admin/logout.
  return (
    <div>
      <div style={{ position: "absolute", top: 16, right: 16, display: "flex", gap: 8 }}>
        {me?.is_admin && <button onClick={() => setView({ name: "admin" })}>Admin</button>}
        <button onClick={async () => { await api.logout(); recheck(); }}>Log out</button>
      </div>
      <Board onOpenTask={(id) => setView({ name: "card", taskId: id })} />
    </div>
  );
}
```

> **Note:** `Board` currently renders its own header (`<h1>📋 Agent Kanban</h1>`). The logout/admin buttons float top-right via absolute positioning to avoid restructuring the Board component. If this looks off, move the header into App and pass it down — but the absolute-positioned approach is the minimum change.

- [ ] **Step 5: WebSocket with token (for cross-origin bearer, if cookie doesn't flow)**

In `web/src/api.ts`, `subscribeWebSocket` should add the bearer token if one is in localStorage (optional — same-origin cookie works without it):
```typescript
export function subscribeWebSocket(
  taskId: number | null,
  onMessage: (evt: { type: string; [k: string]: unknown }) => void,
  options: WSOptions = {}
): WSSubscription {
  // ... existing reconnect logic ...
  const bearer = window.localStorage.getItem("kanban_bearer");
  const qParts = taskId ? [`task_id=${taskId}`] : [];
  if (bearer) qParts.push(`token=${encodeURIComponent(bearer)}`);
  const q = qParts.length ? `?${qParts.join("&")}` : "";
  // ... rest unchanged, uses `q` in the URL ...
```
(For same-origin deployments the session cookie flows automatically; the `?token=` path is a fallback. We don't set `kanban_bearer` in localStorage anywhere in this plan — it's an optional agent-impersonation path. Keep the read so future work can use it.)

- [ ] **Step 6: Verify the build**

Run: `cd web && pnpm build`
Expected: clean.

- [ ] **Step 7: Manual smoke**

Start the server fresh (drop DB, migrate, serve) — observe the bootstrap admin password printed to stdout. Open the UI, log in, mint a token for "codex", copy it. Configure a Codex MCP entry with the bearer header, verify it can `get_next_task` and `claim_task(agent="codex")`.

- [ ] **Step 8: Commit**

```bash
cd /Users/graywrk/src/graywrk_agents_canban
git add web/src/
git commit -m "feat(web): login page, admin panel (tokens + users), route guard"
```

---

## Task 7: README + Phase 4 acceptance

**Files:**
- Modify: `README.md`
- Modify: `docker-compose.yml` (add `SESSION_SECRET`, `PUBLIC_URL`, `BOOTSTRAP_ADMIN_PASSWORD` env)

- [ ] **Step 1: Add an "Authentication" section to README**

After the existing "Coding tasks" section, add:
```markdown
## Authentication

The board requires authentication. Two kinds of principals:

- **Users** (humans): log in with username + password via the web UI. Sessions are signed cookies.
- **Tokens** (agents): opaque bearer tokens, managed in the Admin panel. Each token is bound to an `agent_name`.

### First run

On first startup with an empty database, the board auto-creates an `admin` user and prints a random password to stdout once. Set `AGENT_KANBAN_BOOTSTRAP_ADMIN_PASSWORD` to choose it yourself. Log in, then go to Admin → Users to add more users, and Admin → Tokens to mint tokens for your agents.

### Pointing an agent at the board

Agents authenticate via a bearer token. In your agent's MCP config:

**Codex** (`~/.codex/config.toml`):
```toml
[mcp_servers.kanban]
url = "http://your-host:7331/mcp"
# Codex reads headers from config in newer versions; otherwise set the auth via env.
headers = { Authorization = "Bearer <your-token>" }
```

**Hermes** (`~/.hermes/config.yaml`):
```yaml
mcp_servers:
  kanban:
    url: http://your-host:7331/mcp
    headers:
      Authorization: Bearer <your-token>
```

The token's `agent_name` MUST match the `agent` argument you pass to MCP tools. A token minted with `agent_name=codex` can call `claim_task(agent="codex")` but NOT `claim_task(agent="hermes")`.

### Production env vars

- `SESSION_SECRET` — signing key for session cookies. REQUIRED in production; set a long random string.
- `PUBLIC_URL` — the public base URL (e.g. `https://kanban.example.com`). Controls cookie `Secure` flag.
- `AGENT_KANBAN_BOOTSTRAP_ADMIN_PASSWORD` — first-run admin password (optional; auto-generated if unset).
```

- [ ] **Step 2: Update docker-compose.yml**

Add env to the `app` service:
```yaml
    environment:
      DATABASE_URL: postgresql+asyncpg://kanban:kanban@postgres:5432/kanban
      PORT: "7331"
      SESSION_SECRET: ${SESSION_SECRET:-please-change-me-in-production}
      PUBLIC_URL: ${PUBLIC_URL:-http://localhost:7331}
      AGENT_KANBAN_BOOTSTRAP_ADMIN_PASSWORD: ${AGENT_KANBAN_BOOTSTRAP_ADMIN_PASSWORD:-}
```

- [ ] **Step 3: Verify all acceptance criteria**

Run: `uv run pytest -v` → all passing.
Run: `cd web && pnpm build` → clean.
Run: `uv run ruff check src/ tests/` → clean.

- [ ] **Step 4: Commit**

```bash
git add README.md docker-compose.yml
git commit -m "docs: authentication section; production env vars in compose"
```

---

## Phase 4 Acceptance Criteria

Phase 4 is complete when all of the following hold:

- [ ] `uv run pytest -v` passes (71 prior + new auth tests).
- [ ] `cd web && pnpm build` succeeds.
- [ ] `uv run ruff check src/ tests/` is clean.
- [ ] `GET /api/setup-status` returns `{needs_setup: true}` on an empty DB; the board bootstraps an admin user on first startup and prints the password once.
- [ ] `POST /api/login` with valid creds sets a `kanban_session` cookie; `/api/me` returns the principal; `POST /api/logout` clears it.
- [ ] Every REST endpoint under `/api/*` (except `/api/login`, `/api/setup-status`) returns 401 without credentials.
- [ ] `POST /api/tokens` (admin) returns a plaintext token once; `GET /api/tokens` never returns it.
- [ ] A bearer token from `POST /api/tokens` authenticates `GET /api/me` and `Authorization: Bearer ...` on the MCP endpoint.
- [ ] MCP mutation tools verify `agent == token.agent_name`; mismatch raises (surfaces as a tool error to the agent).
- [ ] MCP read tools (`get_next_task`, `list_tasks`, `get_comments`) require a valid token but do not check `agent`.
- [ ] WebSocket rejects unauthenticated connections with policy-violation close.
- [ ] The UI shows a login page when unauthenticated, an Admin panel (tokens + users) for admins, and route-guards everything else.
- [ ] `SESSION_SECRET`, `PUBLIC_URL`, `AGENT_KANBAN_BOOTSTRAP_ADMIN_PASSWORD` env vars are honored.

---

## Notes for the implementer

- **Migration is required** (Task 1, `0002_auth.py`). This is the first plan that adds migrations since Phase 1. Verify the round-trip (`upgrade → downgrade -1 → upgrade`) before committing.
- **bcrypt cost 12** is the right default as of 2026. Don't lower it for test speed — tests do few hashes.
- **Token scanning**: `verify_token` iterates all Token rows and bcrypt-checks each. For N < 50 tokens this is fine. If N grows, add a `token_prefix` column (first 8 chars, indexed) and pre-filter. Don't optimize prematurely in this plan.
- **`get_http_request` import path**: the MCP SDK moved context helpers between versions. Verify the import resolves; if not, the fallback is a Starlette middleware that sets a contextvar. The plan documents both.
- **Existing route tests break** in Task 4 because they don't authenticate. The fix is the `authed_client` conftest fixture + find/replace. Don't try to make the old `client` fixture auth-transparent — explicit auth is the whole point.
- **The e2e test is skipped in Task 4 and un-skipped in Task 5** — this is intentional sequencing, not a gap.
- **Session middleware ordering**: `SessionMiddleware` must be added so `request.session` works. CORS already exists; order is CORS → Session (Starlette processes middleware in reverse-add order, so add session AFTER CORS).
- **`bootstrap_admin_password` config field**: default empty string means "auto-generate and print". Setting it via env lets operators choose. Never log it after the first print.
- **Token authz failure mode**: a mismatched `agent` raises `PermissionError` inside the tool, which the MCP SDK surfaces as a tool error (not an HTTP 403). This is correct — agents see "your token doesn't match agent X" as a tool result, not an HTTP error. Document this in the agent workflow.
