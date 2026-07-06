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
