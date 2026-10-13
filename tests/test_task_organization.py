"""Task organization: priority + preferred_model ordering, created_by,
project filter, and the new MCP tools (create/update/release/cancel,
projects, progress/artifact reads) and the project PATCH route.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from agent_kanban import mcp_server
from agent_kanban.mcp_server import mcp
from agent_kanban.models import Task, TaskPriority, TaskStatus
from agent_kanban.schemas import TaskCreate
from agent_kanban.services import (
    cancel_task,
    create_task,
    get_next_task,
    release_task,
)

from tests.test_mcp_server import _to_dict


@pytest.fixture(autouse=True)
def _bind_mcp_to_test_db(db_url):
    """Make mcp_server resolve sessions to the per-test throwaway DB.

    Same fixture as test_mcp_server.py: mcp_server resolves the engine from
    current settings on each call; db_url set DATABASE_URL, clearing the
    lru_cache makes the next get_settings() return the test URL.
    """
    from agent_kanban.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _make_task(
    session,
    title: str,
    *,
    status: TaskStatus = TaskStatus.READY,
    priority: TaskPriority = TaskPriority.MEDIUM,
    preferred_model: str | None = None,
    project_id: int | None = None,
    assigned_to: str | None = None,
) -> Task:
    task = Task(
        title=title,
        status=status,
        priority=priority,
        preferred_model=preferred_model,
        project_id=project_id,
        assigned_to=assigned_to,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


# ---- get_next_task ordering ----


async def test_next_task_priority_order_beats_age(session):
    """A newer critical task beats an older medium one."""
    old_medium = await _make_task(session, "old medium")
    new_critical = await _make_task(session, "new critical", priority=TaskPriority.CRITICAL)
    nxt = await get_next_task(session, None, None, None, agent="codex")
    assert nxt is new_critical
    nxt2 = await get_next_task(session, None, None, None, agent=None)
    assert nxt2 is new_critical
    assert old_medium.status == TaskStatus.READY


async def test_next_task_prefers_matching_agent_then_neutral(session):
    """Preference rank: match first, then neutral, then mismatched. None of
    the three groups hide behind another."""
    mismatch = await _make_task(session, "wants hermes", preferred_model="hermes")
    neutral = await _make_task(session, "neutral")
    match = await _make_task(session, "wants codex", preferred_model="codex")
    order = []
    for _ in range(3):
        t = await get_next_task(session, None, None, None, agent="codex")
        order.append(t.title)
        t.status = TaskStatus.IN_PROGRESS
        await session.commit()
    assert order == ["wants codex", "neutral", "wants hermes"]


async def test_next_task_priority_within_preference_group(session):
    """Priority orders inside each preference group."""
    await _make_task(session, "match low", priority=TaskPriority.LOW, preferred_model="codex")
    await _make_task(session, "match high", priority=TaskPriority.HIGH, preferred_model="codex")
    first = await get_next_task(session, None, None, None, agent="codex")
    assert first.title == "match high"


async def test_next_task_priority_full_rank_order(session):
    """critical > high > medium > low, oldest-first inside one rank."""
    await _make_task(session, "low", priority=TaskPriority.LOW)
    await _make_task(session, "medium", priority=TaskPriority.MEDIUM)
    await _make_task(session, "high", priority=TaskPriority.HIGH)
    await _make_task(session, "critical", priority=TaskPriority.CRITICAL)
    order = []
    for _ in range(4):
        t = await get_next_task(session, None, None, None, agent=None)
        order.append(t.title)
        t.status = TaskStatus.IN_PROGRESS
        await session.commit()
    assert order == ["critical", "high", "medium", "low"]


# ---- release_task / cancel_task services ----


async def test_release_task_returns_to_ready(session):
    task = await _make_task(session, "t")
    claim = await session.get(Task, task.id)
    claim.status = TaskStatus.IN_PROGRESS
    claim.claimed_by = "codex"
    await session.commit()

    released = await release_task(session, task.id, "codex")
    assert released.status == TaskStatus.READY
    assert released.claimed_by is None
    assert released.claimed_at is None


async def test_release_task_rejects_non_claimer(session):
    task = await _make_task(session, "t", status=TaskStatus.IN_PROGRESS)
    task.claimed_by = "codex"
    await session.commit()
    with pytest.raises(PermissionError):
        await release_task(session, task.id, "hermes")


async def test_cancel_task_sets_cancelled(session):
    task = await _make_task(session, "t", status=TaskStatus.IN_PROGRESS)
    task.claimed_by = "codex"
    await session.commit()
    cancelled = await cancel_task(session, task.id, "codex")
    assert cancelled.status == TaskStatus.CANCELLED


async def test_cancel_task_rejects_non_claimer(session):
    task = await _make_task(session, "t", status=TaskStatus.IN_PROGRESS)
    task.claimed_by = "codex"
    await session.commit()
    with pytest.raises(PermissionError):
        await cancel_task(session, task.id, "hermes")


# ---- MCP create_task / update_task ----


async def test_mcp_create_task_sets_created_by_and_fields(session):
    result = await mcp.call_tool(
        "create_task",
        {
            "agent": "codex",
            "title": "filed by agent",
            "description": "found a bug",
            "priority": "high",
            "preferred_model": "glm",
        },
    )
    task = _to_dict(result)
    assert task["created_by"] == "codex"
    assert task["priority"] == "high"
    assert task["preferred_model"] == "glm"
    assert task["status"] == "todo"
    row = await session.get(Task, task["id"])
    assert row.created_by == "codex"
    assert row.priority == TaskPriority.HIGH


async def test_mcp_create_task_rejects_wrong_agent(session):
    with pytest.raises(Exception):
        await mcp.call_tool(
            "create_task", {"agent": "not-codex", "title": "x"}
        )


async def test_mcp_update_task_claimer_can_edit(session):
    task = await create_task(session, TaskCreate(title="t"))
    task.status = TaskStatus.IN_PROGRESS
    task.claimed_by = "codex"
    await session.commit()

    result = await mcp.call_tool(
        "update_task",
        {"task_id": task.id, "agent": "codex", "priority": "critical", "title": "renamed"},
    )
    updated = _to_dict(result)
    assert updated["priority"] == "critical"
    assert updated["title"] == "renamed"


async def test_mcp_update_task_rejects_non_claimer(session):
    task = await create_task(session, TaskCreate(title="t"))
    task.status = TaskStatus.IN_PROGRESS
    task.claimed_by = "hermes"
    await session.commit()
    with pytest.raises(Exception):
        await mcp.call_tool(
            "update_task", {"task_id": task.id, "agent": "codex", "title": "nope"}
        )


# ---- MCP release/cancel/projects/reads ----


async def test_mcp_release_task_roundtrip(session):
    task = await _make_task(session, "t", status=TaskStatus.IN_PROGRESS)
    task.claimed_by = "codex"
    await session.commit()

    result = await mcp.call_tool(
        "release_task", {"task_id": task.id, "agent": "codex"}
    )
    released = _to_dict(result)
    assert released["status"] == "ready"
    assert released["claimed_by"] is None


async def test_mcp_cancel_task_roundtrip(session):
    task = await _make_task(session, "t", status=TaskStatus.IN_PROGRESS)
    task.claimed_by = "codex"
    await session.commit()

    result = await mcp.call_tool(
        "cancel_task", {"task_id": task.id, "agent": "codex"}
    )
    assert _to_dict(result)["status"] == "cancelled"


async def test_mcp_projects_list_and_create(session):
    created = _to_dict(
        await mcp.call_tool(
            "create_project",
            {"agent": "codex", "name": "PlastShop", "repo_path": "/srv/repos/ps"},
        )
    )
    assert created["name"] == "PlastShop"
    listed = _to_dict(await mcp.call_tool("list_projects", {}))
    assert [p["name"] for p in listed] == ["PlastShop"]


async def test_mcp_get_task_and_list_progress(session):
    task = await create_task(session, TaskCreate(title="t"))
    got = _to_dict(await mcp.call_tool("get_task", {"task_id": task.id}))
    assert got["id"] == task.id
    missing = _to_dict(await mcp.call_tool("get_task", {"task_id": 99999}))
    assert missing is None
    events = _to_dict(await mcp.call_tool("list_progress", {"task_id": task.id}))
    assert events == []


async def test_mcp_list_artifacts_empty(session):
    task = await create_task(session, TaskCreate(title="t"))
    arts = _to_dict(await mcp.call_tool("list_artifacts", {"task_id": task.id}))
    assert arts == []


async def test_mcp_list_tasks_project_filter(session):
    proj = _to_dict(
        await mcp.call_tool("create_project", {"agent": "codex", "name": "p1"})
    )
    await _make_task(session, "in project", project_id=proj["id"])
    await _make_task(session, "no project")
    listed = _to_dict(
        await mcp.call_tool("list_tasks", {"project_id": proj["id"]})
    )
    assert [t["title"] for t in listed] == ["in project"]


# ---- REST ----


async def test_rest_project_patch(authed_client, session):
    from agent_kanban.schemas import ProjectCreate
    from agent_kanban.services import create_project

    proj = await create_project(session, ProjectCreate(name="before"))
    res = await authed_client.patch(
        f"/api/projects/{proj.id}", json={"name": "after", "default_branch": "main"}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["name"] == "after"
    assert body["default_branch"] == "main"

    missing = await authed_client.patch("/api/projects/99999", json={"name": "x"})
    assert missing.status_code == 404


async def test_rest_task_create_sets_created_by_from_session(authed_client, session):
    res = await authed_client.post(
        "/api/tasks",
        json={"title": "human filed", "priority": "low", "created_by": "spoofed"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["created_by"] == "user"  # principal.agent_name for sessions
    assert body["priority"] == "low"


async def test_rest_list_tasks_project_id_filter(authed_client, session):
    from agent_kanban.schemas import ProjectCreate
    from agent_kanban.services import create_project

    proj = await create_project(session, ProjectCreate(name="p"))
    await _make_task(session, "mine", project_id=proj.id)
    await _make_task(session, "other")
    res = await authed_client.get(f"/api/tasks?project_id={proj.id}")
    assert res.status_code == 200
    titles = [t["title"] for t in res.json()]
    assert titles == ["mine"]
