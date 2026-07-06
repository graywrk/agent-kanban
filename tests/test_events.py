import asyncio
import pytest

from agent_kanban.events import event_bus


@pytest.mark.asyncio
async def test_publish_subscribe_board_channel():
    received = []
    async def consumer():
        async for evt in event_bus.subscribe("board"):
            received.append(evt)
            if len(received) >= 2:
                break

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0.05)  # let subscriber register
    await event_bus.publish("board", {"type": "task_created", "id": 1})
    await event_bus.publish("board", {"type": "task_updated", "id": 2})
    await asyncio.wait_for(task, timeout=1.0)

    assert received[0]["id"] == 1
    assert received[1]["id"] == 2


@pytest.mark.asyncio
async def test_task_channel_isolated():
    received = []
    async def consumer():
        async for evt in event_bus.subscribe("task:5"):
            received.append(evt)
            break

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0.05)
    await event_bus.publish("task:7", {"x": 1})   # wrong channel
    await event_bus.publish("task:5", {"x": 2})   # right channel
    await asyncio.wait_for(task, timeout=1.0)

    assert received == [{"x": 2}]
