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
