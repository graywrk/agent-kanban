from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_kanban.auth import Principal, get_current_principal
from agent_kanban.db import get_session
from agent_kanban.models import ProgressEvent

router = APIRouter(tags=["progress"])


@router.get("/api/tasks/{task_id}/progress")
async def list_progress(
    task_id: int,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
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
            "created_at": e.created_at.isoformat() + "Z",
        }
        for e in result.scalars()
    ]


@router.get("/api/progress/last")
async def last_progress_timestamps(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    """Map task_id → ISO timestamp of its most recent progress_event (for live indicators)."""
    stmt = (
        select(
            ProgressEvent.task_id,
            func.max(ProgressEvent.created_at).label("last_at"),
        )
        .group_by(ProgressEvent.task_id)
    )
    result = await session.execute(stmt)
    return {row.task_id: row.last_at.isoformat() + "Z" for row in result.all()}
