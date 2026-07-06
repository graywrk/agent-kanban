"""Test MCP tools by calling them directly through the FastMCP registry.

FastMCP exposes registered tools via `mcp.call_tool(name, arguments)` (public).
We use that public API and decode the SDK's wrapped return shapes with `_to_dict`.

Return-shape reference for the pinned `mcp` SDK (~1.28). `call_tool` returns
either:
  - a tuple `(unstructured_content, structured_content)` for tools whose
    annotation implies a structured output (`Optional[...]`, `list[...]`);
    structured_content is itself wrapped as `{'result': X}`, OR
  - a list of TextContent blocks for plain `dict`-annotated tools (no
    structured output), OR
  - an empty list when the tool returned an empty list / None-with-no-structure.

`_to_dict` unwraps all of these into the plain value (dict / list / None).
Exceptions raised inside a tool are re-raised by `call_tool` as `ToolError`.

Test isolation: setup/verification goes through the conftest `session` fixture
(resolves dynamically to the per-test throwaway DB). The MCP tools resolve
their own sessions from current settings, which the autouse fixture below
re-points at the same throwaway DB by clearing the settings cache.
"""
import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent_kanban.config import get_settings
from agent_kanban import mcp_server
from agent_kanban.mcp_server import mcp
from agent_kanban.models import TaskStatus
from agent_kanban.schemas import TaskCreate
from agent_kanban.services import create_task, get_task

# Bind the REAL verifier implementations at import time, before the autouse
# `_stub_mcp_principal` fixture (conftest.py) monkeypatches the module-level
# names. The enforcement regression tests below invoke these bound references
# to exercise the genuine logic rather than the stubs.
_real_require_matching_agent = mcp_server._require_matching_agent
_real_require_any_principal = mcp_server._require_any_principal
_real_mcp_principal = mcp_server._mcp_principal


def _to_dict(result):
    """Decode the FastMCP-wrapped result of `call_tool` into a plain value."""
    # Structured wrap: (unstructured_content, structured_content).
    if isinstance(result, tuple) and len(result) == 2:
        structured = result[1]
        # SDK wraps structured payload as {'result': X} for Optional/list tools.
        if isinstance(structured, dict) and set(structured.keys()) == {"result"}:
            return structured["result"]
        return structured
    # Plain list of content blocks (or empty list).
    if isinstance(result, list):
        if not result:
            return None
        if all(hasattr(block, "text") for block in result):
            decoded = []
            for block in result:
                try:
                    decoded.append(json.loads(block.text))
                except (ValueError, TypeError):
                    decoded.append(block.text)
            # Single-element -> unwrap to the dict itself.
            return decoded[0] if len(decoded) == 1 else decoded
    if hasattr(result, "model_dump"):
        return result.model_dump()
    return result


def _fresh_session_factory():
    """Build a session factory against the currently-configured test DB.

    Used to verify DB state after an MCP tool committed via its own session.
    """
    from agent_kanban.db import _engine_for

    return async_sessionmaker(
        _engine_for(get_settings().database_url),
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest.fixture(autouse=True)
def _bind_mcp_to_test_db(db_url):
    """Make mcp_server resolve sessions to the per-test throwaway DB.

    mcp_server resolves the engine from current settings on each call (matching
    the routes pattern). db_url set DATABASE_URL; clearing the lru_cache here
    makes the next get_settings() return the test URL.
    """
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# The MCP principal verifiers are stubbed for in-process `mcp.call_tool` by the
# autouse `_stub_mcp_principal` fixture in tests/conftest.py (shared across all
# test modules that invoke MCP tools directly).


@pytest.mark.asyncio
async def test_get_next_task_returns_null_when_none_ready(session: AsyncSession):
    await create_task(session, TaskCreate(title="x", status=TaskStatus.TODO))
    result = await mcp.call_tool("get_next_task", {})
    data = _to_dict(result)
    assert data is None


@pytest.mark.asyncio
async def test_get_next_task_returns_ready_task(session: AsyncSession):
    await create_task(session, TaskCreate(title="ready one", status=TaskStatus.READY))
    result = await mcp.call_tool("get_next_task", {})
    data = _to_dict(result)
    assert isinstance(data, dict)
    assert data["title"] == "ready one"
    assert data["status"] == "ready"


@pytest.mark.asyncio
async def test_claim_task_via_mcp(session: AsyncSession):
    t = await create_task(session, TaskCreate(title="x", status=TaskStatus.READY))
    result = await mcp.call_tool("claim_task", {"task_id": t.id, "agent": "codex"})
    data = _to_dict(result)
    assert isinstance(data, dict)
    assert data["ok"] is True
    assert data["task"]["claimed_by"] == "codex"
    assert data["task"]["status"] == "in_progress"


@pytest.mark.asyncio
async def test_claim_task_returns_repo_path_and_base_branch(session: AsyncSession):
    """Spec §6.2: agent receives repo_path and base_branch on claim."""
    t = await create_task(
        session,
        TaskCreate(
            title="coding task",
            status=TaskStatus.READY,
            repo_path="/path/to/repo",
            base_branch="main",
        ),
    )
    result = await mcp.call_tool("claim_task", {"task_id": t.id, "agent": "codex"})
    data = _to_dict(result)
    # claim_task returns {ok, reason, task}; the task dict may sit at top level
    # or be nested under "result" depending on SDK wrapping for the pinned version.
    task_dict = (
        data.get("task", data) if isinstance(data, dict) else data
    )
    if not isinstance(task_dict, dict) or "repo_path" not in task_dict:
        task_dict = data.get("result", {}).get("task", task_dict)
    assert task_dict.get("repo_path") == "/path/to/repo"
    assert task_dict.get("base_branch") == "main"


@pytest.mark.asyncio
async def test_claim_task_rejects_when_not_ready(session: AsyncSession):
    t = await create_task(session, TaskCreate(title="x", status=TaskStatus.TODO))
    result = await mcp.call_tool("claim_task", {"task_id": t.id, "agent": "codex"})
    data = _to_dict(result)
    assert data["ok"] is False


@pytest.mark.asyncio
async def test_post_progress_rejects_wrong_agent(session: AsyncSession):
    t = await create_task(session, TaskCreate(title="x", status=TaskStatus.READY))
    await mcp.call_tool("claim_task", {"task_id": t.id, "agent": "codex"})
    with pytest.raises(Exception):
        await mcp.call_tool(
            "post_progress",
            {
                "task_id": t.id,
                "agent": "hermes",
                "kind": "text",
                "content": "intrusion",
            },
        )


@pytest.mark.asyncio
async def test_post_progress_via_mcp(session: AsyncSession):
    t = await create_task(session, TaskCreate(title="x", status=TaskStatus.READY))
    await mcp.call_tool("claim_task", {"task_id": t.id, "agent": "codex"})
    result = await mcp.call_tool(
        "post_progress",
        {"task_id": t.id, "agent": "codex", "kind": "text", "content": "working"},
    )
    data = _to_dict(result)
    assert data["kind"] == "text"
    assert "id" in data and "created_at" in data


@pytest.mark.asyncio
async def test_complete_task_via_mcp(session: AsyncSession):
    t = await create_task(session, TaskCreate(title="x", status=TaskStatus.READY))
    await mcp.call_tool("claim_task", {"task_id": t.id, "agent": "codex"})
    await mcp.call_tool(
        "complete_task", {"task_id": t.id, "agent": "codex", "summary": "done"}
    )
    # Verify DB state via a fresh session so we read the committed row
    # (the MCP tool committed through its own session/connection).
    async with _fresh_session_factory()() as s:
        t2 = await get_task(s, t.id)
        assert t2.status == TaskStatus.DONE


@pytest.mark.asyncio
async def test_request_review_via_mcp(session: AsyncSession):
    t = await create_task(session, TaskCreate(title="x", status=TaskStatus.READY))
    await mcp.call_tool("claim_task", {"task_id": t.id, "agent": "codex"})
    await mcp.call_tool("request_review", {"task_id": t.id, "agent": "codex"})
    async with _fresh_session_factory()() as s:
        t2 = await get_task(s, t.id)
        assert t2.status == TaskStatus.REVIEW


@pytest.mark.asyncio
async def test_get_comments_and_post_comment_via_mcp(session: AsyncSession):
    t = await create_task(session, TaskCreate(title="x", status=TaskStatus.READY))
    await mcp.call_tool(
        "post_comment", {"task_id": t.id, "agent": "codex", "content": "hello"}
    )
    result = await mcp.call_tool("get_comments", {"task_id": t.id})
    data = _to_dict(result)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["content"] == "hello"
    assert data[0]["author"] == "codex"


@pytest.mark.asyncio
async def test_list_tasks_via_mcp(session: AsyncSession):
    await create_task(session, TaskCreate(title="a", status=TaskStatus.TODO))
    await create_task(session, TaskCreate(title="b", status=TaskStatus.READY, tags=["ui"]))
    result = await mcp.call_tool("list_tasks", {})
    data = _to_dict(result)
    assert isinstance(data, list)
    assert len(data) == 2
    # Filter by status.
    result = await mcp.call_tool("list_tasks", {"status": "ready"})
    data = _to_dict(result)
    assert len(data) == 1
    assert data[0]["title"] == "b"
    # Filter by tags_any.
    result = await mcp.call_tool("list_tasks", {"tags_any": ["ui"]})
    data = _to_dict(result)
    assert len(data) == 1
    assert data[0]["tags"] == ["ui"]


@pytest.mark.asyncio
async def test_post_artifact_rejects_wrong_agent(session: AsyncSession):
    t = await create_task(session, TaskCreate(title="x", status=TaskStatus.READY))
    await mcp.call_tool("claim_task", {"task_id": t.id, "agent": "codex"})
    with pytest.raises(Exception):
        await mcp.call_tool(
            "post_artifact",
            {
                "task_id": t.id,
                "agent": "hermes",
                "kind": "file",
                "path": "/tmp/x",
            },
        )


@pytest.mark.asyncio
async def test_tools_list_core_tools_registered():
    """Sanity: all core MCP tools (11) are registered with FastMCP."""
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    expected = {
        "get_next_task",
        "claim_task",
        "list_tasks",
        "post_progress",
        "complete_task",
        "request_review",
        "get_comments",
        "post_comment",
        "post_artifact",
        "set_task_branch",
        "set_task_pr",
    }
    assert expected.issubset(names), f"missing: {expected - names}"
    assert len(names) == 11, f"expected 11 tools, got {len(names)}: {names}"


@pytest.mark.asyncio
async def test_set_task_branch_via_mcp(session: AsyncSession):
    t = await create_task(session, TaskCreate(title="t", status=TaskStatus.READY))
    await mcp.call_tool("claim_task", {"task_id": t.id, "agent": "codex"})
    result = await mcp.call_tool(
        "set_task_branch", {"task_id": t.id, "agent": "codex", "branch": "feat/x"}
    )
    data = _to_dict(result)
    # The branch field may sit at top level or be nested under "result"
    # depending on the SDK wrapping for the pinned version; both are fine.
    flat = data if isinstance(data, dict) and "branch" in data else data.get("result", data)
    assert flat["branch"] == "feat/x"


@pytest.mark.asyncio
async def test_set_task_branch_rejects_non_claimer(session: AsyncSession):
    t = await create_task(session, TaskCreate(title="t", status=TaskStatus.READY))
    await mcp.call_tool("claim_task", {"task_id": t.id, "agent": "codex"})
    with pytest.raises(Exception):
        await mcp.call_tool(
            "set_task_branch",
            {"task_id": t.id, "agent": "hermes", "branch": "feat/y"},
        )


@pytest.mark.asyncio
async def test_set_task_pr_via_mcp(session: AsyncSession):
    t = await create_task(session, TaskCreate(title="t", status=TaskStatus.READY))
    await mcp.call_tool("claim_task", {"task_id": t.id, "agent": "codex"})
    result = await mcp.call_tool(
        "set_task_pr",
        {
            "task_id": t.id,
            "agent": "codex",
            "pr_url": "https://github.com/x/y/pull/1",
            "status": "open",
        },
    )
    data = _to_dict(result)
    flat = (
        data if isinstance(data, dict) and "pr_url" in data else data.get("result", data)
    )
    assert flat["pr_url"] == "https://github.com/x/y/pull/1"
    assert flat["pr_status"] == "open"


# --- Enforcement regression tests -------------------------------------------
# These intentionally bypass the autouse `_stub_mcp_principal` stub by invoking
# the real verifier functions against the real `_mcp_principal` ContextVar.
# They prove the agent-param-spoofing hole is actually closed: with no token
# (empty ContextVar) every tool is rejected, and a mismatched agent is rejected
# even when a principal is present.
@pytest.mark.asyncio
async def test_verifier_rejects_unauthenticated(session: AsyncSession):
    assert _real_mcp_principal.get() is None  # no HTTP middleware in-process
    with pytest.raises(PermissionError, match="authentication required"):
        await _real_require_any_principal()


@pytest.mark.asyncio
async def test_matching_verifier_rejects_mismatched_agent(session: AsyncSession):
    from agent_kanban.auth import Principal

    token = _real_mcp_principal.set(Principal(kind="token", agent_name="codex"))
    try:
        # Correct agent passes.
        p = await _real_require_matching_agent("codex")
        assert p.agent_name == "codex"
        # Spoofed agent is rejected — closes the param-spoofing hole.
        with pytest.raises(PermissionError, match="does not match"):
            await _real_require_matching_agent("hermes")
    finally:
        _real_mcp_principal.reset(token)
