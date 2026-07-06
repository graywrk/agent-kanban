
import pytest
from sqlmodel import select

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


@pytest.mark.asyncio
async def test_resolve_bearer_uses_prefix_filter(session):
    """The prefix index narrows candidates before bcrypt."""
    from agent_kanban.auth import _resolve_bearer, generate_token, hash_token
    from agent_kanban.models import Token, User

    # The token table requires created_by_user_id (NOT NULL FK), so seed a user.
    session.add(User(username="owner", password_hash="x", is_admin=True))
    await session.commit()
    user_id = (await session.execute(select(User))).scalars().first().id

    # Two tokens with different prefixes.
    t1 = generate_token()
    t2 = generate_token()
    session.add(Token(agent_name="a", token_hash=hash_token(t1), token_prefix=t1[:8], created_by_user_id=user_id))
    session.add(Token(agent_name="b", token_hash=hash_token(t2), token_prefix=t2[:8], created_by_user_id=user_id))
    await session.commit()
    p = await _resolve_bearer(session, t1)
    assert p is not None and p.agent_name == "a"
    p = await _resolve_bearer(session, t2)
    assert p is not None and p.agent_name == "b"
    p = await _resolve_bearer(session, "not-a-real-token")
    assert p is None


@pytest.mark.asyncio
async def test_resolve_bearer_falls_back_for_legacy_empty_prefix(session):
    """Tokens minted before Phase 5 (empty token_prefix) still resolve via full scan.

    The prefix-indexed fast path finds nothing for an empty-prefix row, so
    _resolve_bearer falls back to scanning all token_prefix="" rows and
    bcrypt-verifies each — keeping legacy tokens working.
    """
    from agent_kanban.auth import _resolve_bearer, generate_token, hash_token
    from agent_kanban.models import Token, User

    # The token table requires created_by_user_id (NOT NULL FK), so seed a user.
    session.add(User(username="legacy-owner", password_hash="x", is_admin=True))
    await session.commit()
    user_id = (await session.execute(select(User))).scalars().first().id

    plain = generate_token()
    # Legacy row: token_prefix not set (empty string).
    session.add(
        Token(
            agent_name="legacy",
            token_hash=hash_token(plain),
            token_prefix="",
            created_by_user_id=user_id,
        )
    )
    await session.commit()
    p = await _resolve_bearer(session, plain)
    assert p is not None
    assert p.agent_name == "legacy"
