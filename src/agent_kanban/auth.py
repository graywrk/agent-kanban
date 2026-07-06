"""Authentication: password hashing, token generation/verification, Principal resolution."""
import secrets
import time
from datetime import UTC, datetime
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
