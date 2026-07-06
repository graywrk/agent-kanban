import pytest


@pytest.mark.asyncio
async def test_progress_empty_for_new_task(authed_client):
    r = await authed_client.post("/api/tasks", json={"title": "t"})
    task_id = r.json()["id"]
    r = await authed_client.get(f"/api/tasks/{task_id}/progress")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_last_progress_timestamps_has_z_suffix(authed_client):
    """Live indicator relies on UTC 'Z' suffix to avoid local-time parse in JS."""
    r = await authed_client.post("/api/tasks", json={"title": "t"})
    task_id = r.json()["id"]
    # Move to ready, claim, post progress.
    await authed_client.patch(f"/api/tasks/{task_id}", json={"status": "ready"})
    from agent_kanban.mcp_server import mcp
    await mcp.call_tool("claim_task", {"task_id": task_id, "agent": "codex"})
    await mcp.call_tool(
        "post_progress",
        {"task_id": task_id, "agent": "codex", "kind": "text", "content": "hi"},
    )
    r = await authed_client.get("/api/progress/last")
    assert r.status_code == 200
    ts = r.json()[str(task_id)]
    assert ts.endswith("Z"), f"expected UTC 'Z' suffix, got {ts!r}"


@pytest.mark.asyncio
async def test_list_progress_has_z_suffix(authed_client):
    """created_at in list_progress must end with 'Z' so JS parses as UTC."""
    r = await authed_client.post("/api/tasks", json={"title": "t"})
    task_id = r.json()["id"]
    await authed_client.patch(f"/api/tasks/{task_id}", json={"status": "ready"})
    from agent_kanban.mcp_server import mcp
    await mcp.call_tool("claim_task", {"task_id": task_id, "agent": "codex"})
    await mcp.call_tool(
        "post_progress",
        {"task_id": task_id, "agent": "codex", "kind": "text", "content": "hi"},
    )
    r = await authed_client.get(f"/api/tasks/{task_id}/progress")
    assert r.status_code == 200
    events = r.json()
    assert len(events) == 1
    ts = events[0]["created_at"]
    assert ts.endswith("Z"), f"expected UTC 'Z' suffix, got {ts!r}"
