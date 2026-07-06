import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agent_kanban.models import TaskStatus
from agent_kanban.schemas import ArtifactCreate, ProgressCreate, TaskCreate
from agent_kanban.services import (
    claim_task,
    complete_task,
    create_task,
    get_next_task,
    post_artifact,
    post_progress,
    request_review,
    update_task,
)
from agent_kanban.models import ProgressKind


@pytest.mark.asyncio
async def test_create_task_defaults_to_todo(session: AsyncSession):
    t = await create_task(session, TaskCreate(title="hi"))
    assert t.status == TaskStatus.TODO
    assert t.tags == []


@pytest.mark.asyncio
async def test_get_next_task_returns_only_ready(session: AsyncSession):
    a = await create_task(session, TaskCreate(title="a", status=TaskStatus.TODO))
    b = await create_task(session, TaskCreate(title="b", status=TaskStatus.READY))
    nxt = await get_next_task(session, None, None, None)
    assert nxt is not None
    assert nxt.id == b.id


@pytest.mark.asyncio
async def test_get_next_task_filters_by_tag(session: AsyncSession):
    await create_task(session, TaskCreate(title="x", status=TaskStatus.READY, tags=["ui"]))
    await create_task(session, TaskCreate(title="y", status=TaskStatus.READY, tags=["backend"]))
    nxt = await get_next_task(session, tags_any=["backend"], tags_all=None, exclude_tags=None)
    assert nxt is not None
    assert nxt.tags == ["backend"]


@pytest.mark.asyncio
async def test_claim_task_atomic_and_authorizes(session: AsyncSession):
    t = await create_task(session, TaskCreate(title="t", status=TaskStatus.READY))
    r1 = await claim_task(session, t.id, "codex")
    assert r1.ok is True
    assert r1.task.claimed_by == "codex"
    assert r1.task.status == TaskStatus.IN_PROGRESS

    # Second claim attempt fails.
    r2 = await claim_task(session, t.id, "hermes")
    assert r2.ok is False
    assert "already" in (r2.reason or "").lower() or "not ready" in (r2.reason or "").lower()


@pytest.mark.asyncio
async def test_post_progress_requires_claimer(session: AsyncSession):
    t = await create_task(session, TaskCreate(title="t", status=TaskStatus.READY))
    await claim_task(session, t.id, "codex")

    # Wrong agent rejected.
    with pytest.raises(PermissionError):
        await post_progress(
            session,
            t.id,
            ProgressCreate(agent="hermes", kind=ProgressKind.TEXT, content="hi"),
        )

    # Right agent succeeds.
    ev = await post_progress(
        session,
        t.id,
        ProgressCreate(agent="codex", kind=ProgressKind.TEXT, content="hi"),
    )
    assert ev.payload["content"] == "hi"


@pytest.mark.asyncio
async def test_complete_task_sets_done(session: AsyncSession):
    t = await create_task(session, TaskCreate(title="t", status=TaskStatus.READY))
    await claim_task(session, t.id, "codex")
    done = await complete_task(session, t.id, "codex", summary="all done")
    assert done.status == TaskStatus.DONE


@pytest.mark.asyncio
async def test_complete_task_rejects_non_claimer(session: AsyncSession):
    t = await create_task(session, TaskCreate(title="t", status=TaskStatus.READY))
    await claim_task(session, t.id, "codex")
    with pytest.raises(PermissionError):
        await complete_task(session, t.id, "hermes")


@pytest.mark.asyncio
async def test_request_review_sets_review(session: AsyncSession):
    t = await create_task(session, TaskCreate(title="t", status=TaskStatus.READY))
    await claim_task(session, t.id, "codex")
    out = await request_review(session, t.id, "codex", summary="please check")
    assert out.status == TaskStatus.REVIEW


@pytest.mark.asyncio
async def test_post_artifact_rejects_path_outside_sandbox(session: AsyncSession):
    t = await create_task(session, TaskCreate(title="t", status=TaskStatus.READY))
    await claim_task(session, t.id, "codex")
    with pytest.raises(ValueError):
        await post_artifact(
            session,
            t.id,
            ArtifactCreate(agent="codex", kind="log", path="/etc/passwd"),
        )
