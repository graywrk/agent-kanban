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
