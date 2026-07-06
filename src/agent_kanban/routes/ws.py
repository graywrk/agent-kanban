"""WebSocket endpoint for live updates."""
from contextlib import suppress
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from agent_kanban.auth import _resolve_cookie, resolve_ticket
from agent_kanban.db import AsyncSessionLocal
from agent_kanban.events import event_bus

router = APIRouter(tags=["ws"])


@router.websocket("/ws")
async def ws_endpoint(
    websocket: WebSocket,
    task_id: Optional[int] = None,
    ticket: Optional[str] = Query(None, description="Single-use WS ticket from POST /api/ws-ticket"),
):
    # 1. Ticket path (preferred) — no DB hit, single-use nonce.
    if ticket:
        principal = resolve_ticket(ticket)
        if principal is not None:
            await websocket.accept()
            await _stream(websocket, task_id)
            return
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 2. Session cookie fallback (same-origin deployments).
    async with AsyncSessionLocal() as session:
        user_id = websocket.session.get("user_id") if hasattr(websocket, "session") else None
        ok = user_id is not None and (await _resolve_cookie(session, int(user_id))) is not None
    if not ok:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()
    await _stream(websocket, task_id)


async def _stream(websocket: WebSocket, task_id: Optional[int]) -> None:
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
