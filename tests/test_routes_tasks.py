import pytest


@pytest.mark.asyncio
async def test_create_and_list_tasks(authed_client):
    r = await authed_client.post(
        "/api/tasks",
        json={"title": "do thing", "tags": ["ui"]},
    )
    assert r.status_code == 201
    created = r.json()
    assert created["status"] == "todo"
    assert created["tags"] == ["ui"]

    r = await authed_client.get("/api/tasks")
    assert r.status_code == 200
    tasks = r.json()
    assert len(tasks) == 1
    assert tasks[0]["id"] == created["id"]


@pytest.mark.asyncio
async def test_update_task_status(authed_client):
    r = await authed_client.post("/api/tasks", json={"title": "t"})
    task_id = r.json()["id"]
    r = await authed_client.patch(f"/api/tasks/{task_id}", json={"status": "ready"})
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_get_task_by_id(authed_client):
    r = await authed_client.post("/api/tasks", json={"title": "t"})
    task_id = r.json()["id"]
    r = await authed_client.get(f"/api/tasks/{task_id}")
    assert r.status_code == 200
    assert r.json()["title"] == "t"


@pytest.mark.asyncio
async def test_get_task_404(authed_client):
    r = await authed_client.get("/api/tasks/9999")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_tasks_invalid_status_returns_422(authed_client):
    r = await authed_client.get("/api/tasks?status=bogus")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_list_tasks_filter_by_status(authed_client):
    await authed_client.post("/api/tasks", json={"title": "t1"})
    r = await authed_client.get("/api/tasks?status=ready")
    assert r.status_code == 200
    assert r.json() == []
