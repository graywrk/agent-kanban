import pytest
from httpx import ASGITransport, AsyncClient

from agent_kanban.server import create_app


@pytest.fixture
async def client(db_url):
    # Re-import config so the env-var override takes effect.
    from agent_kanban.config import get_settings
    get_settings.cache_clear()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_create_and_list_tasks(client):
    r = await client.post(
        "/api/tasks",
        json={"title": "do thing", "tags": ["ui"]},
    )
    assert r.status_code == 201
    created = r.json()
    assert created["status"] == "todo"
    assert created["tags"] == ["ui"]

    r = await client.get("/api/tasks")
    assert r.status_code == 200
    tasks = r.json()
    assert len(tasks) == 1
    assert tasks[0]["id"] == created["id"]


@pytest.mark.asyncio
async def test_update_task_status(client):
    r = await client.post("/api/tasks", json={"title": "t"})
    task_id = r.json()["id"]
    r = await client.patch(f"/api/tasks/{task_id}", json={"status": "ready"})
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_get_task_by_id(client):
    r = await client.post("/api/tasks", json={"title": "t"})
    task_id = r.json()["id"]
    r = await client.get(f"/api/tasks/{task_id}")
    assert r.status_code == 200
    assert r.json()["title"] == "t"


@pytest.mark.asyncio
async def test_get_task_404(client):
    r = await client.get("/api/tasks/9999")
    assert r.status_code == 404
