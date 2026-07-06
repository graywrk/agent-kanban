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
async def test_progress_empty_for_new_task(client):
    r = await client.post("/api/tasks", json={"title": "t"})
    task_id = r.json()["id"]
    r = await client.get(f"/api/tasks/{task_id}/progress")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_last_progress_timestamps_has_z_suffix(client):
    """Live indicator relies on UTC 'Z' suffix to avoid local-time parse in JS."""
    r = await client.post("/api/tasks", json={"title": "t"})
    task_id = r.json()["id"]
    # Move to ready, claim, post progress.
    await client.patch(f"/api/tasks/{task_id}", json={"status": "ready"})
    from agent_kanban.mcp_server import mcp
    await mcp.call_tool("claim_task", {"task_id": task_id, "agent": "codex"})
    await mcp.call_tool(
        "post_progress",
        {"task_id": task_id, "agent": "codex", "kind": "text", "content": "hi"},
    )
    r = await client.get("/api/progress/last")
    assert r.status_code == 200
    ts = r.json()[str(task_id)]
    assert ts.endswith("Z"), f"expected UTC 'Z' suffix, got {ts!r}"


@pytest.mark.asyncio
async def test_list_progress_has_z_suffix(client):
    """created_at in list_progress must end with 'Z' so JS parses as UTC."""
    r = await client.post("/api/tasks", json={"title": "t"})
    task_id = r.json()["id"]
    await client.patch(f"/api/tasks/{task_id}", json={"status": "ready"})
    from agent_kanban.mcp_server import mcp
    await mcp.call_tool("claim_task", {"task_id": task_id, "agent": "codex"})
    await mcp.call_tool(
        "post_progress",
        {"task_id": task_id, "agent": "codex", "kind": "text", "content": "hi"},
    )
    r = await client.get(f"/api/tasks/{task_id}/progress")
    assert r.status_code == 200
    events = r.json()
    assert len(events) == 1
    ts = events[0]["created_at"]
    assert ts.endswith("Z"), f"expected UTC 'Z' suffix, got {ts!r}"
