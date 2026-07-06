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
async def test_post_and_list_comments(client):
    r = await client.post("/api/tasks", json={"title": "t"})
    task_id = r.json()["id"]

    r = await client.post(
        f"/api/tasks/{task_id}/comments",
        json={"author": "user", "content": "hello"},
    )
    assert r.status_code == 201
    assert r.json()["author"] == "user"

    r = await client.get(f"/api/tasks/{task_id}/comments")
    assert r.status_code == 200
    assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_comment_on_review_task_moves_to_in_progress(client):
    # Create a task and move it to review directly.
    r = await client.post("/api/tasks", json={"title": "t"})
    task_id = r.json()["id"]
    await client.patch(f"/api/tasks/{task_id}", json={"status": "review"})

    # Post a comment with no explicit status.
    r = await client.post(
        f"/api/tasks/{task_id}/comments",
        json={"author": "user", "content": "please also handle the empty case"},
    )
    assert r.status_code == 201

    # Task should now be in_progress.
    r = await client.get(f"/api/tasks/{task_id}")
    assert r.json()["status"] == "in_progress"


@pytest.mark.asyncio
async def test_comment_with_explicit_ready_status(client):
    r = await client.post("/api/tasks", json={"title": "t"})
    task_id = r.json()["id"]
    await client.patch(f"/api/tasks/{task_id}", json={"status": "review"})

    r = await client.post(
        f"/api/tasks/{task_id}/comments?status=ready",
        json={"author": "user", "content": "redo it"},
    )
    assert r.status_code == 201
    r = await client.get(f"/api/tasks/{task_id}")
    assert r.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_comment_on_non_review_task_does_not_change_status(client):
    r = await client.post("/api/tasks", json={"title": "t"})
    task_id = r.json()["id"]
    # Task is in 'todo'.
    r = await client.post(
        f"/api/tasks/{task_id}/comments",
        json={"author": "user", "content": "hi"},
    )
    assert r.status_code == 201
    r = await client.get(f"/api/tasks/{task_id}")
    assert r.json()["status"] == "todo"


@pytest.mark.asyncio
async def test_comment_with_invalid_status_returns_422(client):
    r = await client.post("/api/tasks", json={"title": "t"})
    task_id = r.json()["id"]
    r = await client.post(
        f"/api/tasks/{task_id}/comments?status=bogus",
        json={"author": "user", "content": "x"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_post_comment_with_status_is_atomic(session):
    """If the status update would fail, the comment must not be persisted either."""
    from agent_kanban.services import post_comment_with_status
    from agent_kanban.models import TaskStatus
    # Use a non-existent task_id to trigger a ValueError inside the service
    # (get_task raises). The comment must NOT be persisted.
    from sqlmodel import select
    from agent_kanban.models import Comment
    with pytest.raises(ValueError):
        await post_comment_with_status(
            session, 999999, "user", "should not persist", TaskStatus.IN_PROGRESS
        )
    # Verify no comment was committed for the ghost task.
    stmt = select(Comment).where(Comment.task_id == 999999)
    result = await session.execute(stmt)
    assert result.scalars().all() == []
