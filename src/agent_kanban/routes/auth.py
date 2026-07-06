"""Auth REST routes: setup-status, login, logout, me, tokens CRUD, users CRUD."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
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


# ---- Login / logout (public) ----
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
        token_prefix=plain[:8],
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
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(404, "user not found")
    if target.is_admin:
        admin_count = (
            await session.execute(select(func.count(User.id)).where(User.is_admin == True))  # noqa: E712
        ).scalar_one()
        if admin_count <= 1:
            raise HTTPException(400, "cannot delete the last admin")
    await session.delete(target)
    await session.commit()
    return {"ok": True}
