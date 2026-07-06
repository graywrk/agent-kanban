
import pytest
from starlette.testclient import TestClient

from agent_kanban.server import create_app


@pytest.mark.asyncio
async def test_ws_board_channel_receives_task_created(db_url):
    from agent_kanban.config import get_settings
    get_settings.cache_clear()
    app = create_app()

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            # Trigger a task creation via REST.
            r = client.post("/api/tasks", json={"title": "x"})
            assert r.status_code == 201
            msg = ws.receive_json()
            assert msg["type"] == "task_created"
            assert msg["task_id"] == r.json()["id"]


@pytest.mark.asyncio
async def test_ws_task_channel_filtered(db_url):
    from agent_kanban.config import get_settings
    get_settings.cache_clear()
    app = create_app()

    with TestClient(app) as client:
        # Create two tasks first.
        t1 = client.post("/api/tasks", json={"title": "a"}).json()
        t2 = client.post("/api/tasks", json={"title": "b"}).json()

        with client.websocket_connect(f"/ws?task_id={t1['id']}") as ws:
            # Comment on t2 — should NOT arrive on t1's channel.
            client.post(
                f"/api/tasks/{t2['id']}/comments",
                json={"author": "user", "content": "for t2"},
            )
            # Comment on t1 — SHOULD arrive.
            client.post(
                f"/api/tasks/{t1['id']}/comments",
                json={"author": "user", "content": "for t1"},
            )
            msg = ws.receive_json()
            assert msg["type"] == "comment"
            assert msg["author"] == "user"
