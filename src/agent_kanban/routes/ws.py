"""WebSocket endpoint for live updates."""
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
            await websocket.send_json(evt)
    except WebSocketDisconnect:
        pass
