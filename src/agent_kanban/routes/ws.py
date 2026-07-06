"""WebSocket endpoint for live updates."""
from contextlib import suppress
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from agent_kanban.auth import _resolve_bearer, _resolve_cookie
from agent_kanban.db import AsyncSessionLocal
from agent_kanban.events import event_bus

router = APIRouter(tags=["ws"])


async def _ws_principal(websocket: WebSocket, token: Optional[str]) -> bool:
    """Return True if the websocket carries a valid session cookie or bearer token."""
    async with AsyncSessionLocal() as session:
        # Session cookie first.
        user_id = websocket.session.get("user_id") if hasattr(websocket, "session") else None
        if user_id is not None:
            p = await _resolve_cookie(session, int(user_id))
            if p is not None:
                return True
        if token:
            p = await _resolve_bearer(session, token)
            if p is not None:
                return True
    return False


@router.websocket("/ws")
async def ws_endpoint(
    websocket: WebSocket,
    task_id: Optional[int] = None,
    token: Optional[str] = Query(None),
):
    ok = await _ws_principal(websocket, token)
    if not ok:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
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
        with suppress(Exception):
            await subscriber.aclose()
