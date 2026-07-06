"""WebSocket endpoint for live updates."""
from contextlib import suppress
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from agent_kanban.events import event_bus

router = APIRouter(tags=["ws"])


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket, task_id: Optional[int] = None):
    await websocket.accept()
    channel = f"task:{task_id}" if task_id else "board"
    subscriber = event_bus.subscribe(channel)
    try:
        async for evt in subscriber:
            with suppress(Exception):
                await websocket.send_json(evt)
    except WebSocketDisconnect:
        pass
    finally:
        # Explicit cleanup: close the async iterator so the bus's finally
        # block removes the queue from the subscriber set immediately,
        # rather than waiting for GC.
        with suppress(Exception):
            await subscriber.aclose()
