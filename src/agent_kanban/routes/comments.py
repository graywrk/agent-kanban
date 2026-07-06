"""REST routes for comments."""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from agent_kanban.db import get_session
from agent_kanban.models import TaskStatus
from agent_kanban.schemas import CommentCreate, CommentRead, TaskUpdate
from agent_kanban.services import get_task, list_comments, post_comment, update_task

router = APIRouter(prefix="/api/tasks/{task_id}/comments", tags=["comments"])


@router.get("", response_model=list[CommentRead])
async def get_comments(
    task_id: int,
    since_id: Optional[int] = None,
    session: AsyncSession = Depends(get_session),
):
    # UI doesn't mark comments seen (only agents do via MCP).
    return await list_comments(session, task_id, since_id, mark_seen_by=None)


@router.post("", response_model=CommentRead, status_code=201)
async def add_comment(
    task_id: int,
    data: CommentCreate,
    status: Optional[str] = Query(
        None, description="Override task status after comment. If omitted, review→in_progress."
    ),
    session: AsyncSession = Depends(get_session),
):
    # UI posts as author "user" unless specified.
    if data.author == "":
        data.author = "user"
    comment = await post_comment(session, task_id, data.author, data.content)

    # Resolve the target status: explicit query param wins; else auto review→in_progress.
    if status is not None:
        target = TaskStatus(status)
    else:
        task = await get_task(session, task_id)
        target = TaskStatus.IN_PROGRESS if task.status == TaskStatus.REVIEW else None

    if target is not None:
        await update_task(session, task_id, TaskUpdate(status=target))
    return comment
