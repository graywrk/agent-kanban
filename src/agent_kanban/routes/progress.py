"""REST routes for progress events (read-only in the UI)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from agent_kanban.db import get_session
from agent_kanban.models import ProgressEvent

router = APIRouter(prefix="/api/tasks/{task_id}/progress", tags=["progress"])


@router.get("")
async def list_progress(task_id: int, session: AsyncSession = Depends(get_session)):
    stmt = (
        select(ProgressEvent)
        .where(ProgressEvent.task_id == task_id)
        .order_by(ProgressEvent.created_at)
    )
    result = await session.execute(stmt)
    return [
        {
            "id": e.id,
            "task_id": e.task_id,
            "agent": e.agent,
            "kind": e.kind.value if hasattr(e.kind, "value") else e.kind,
            "payload": e.payload,
            "created_at": e.created_at.isoformat(),
        }
        for e in result.scalars()
    ]
