"""REST routes for comments."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from agent_kanban.db import get_session
from agent_kanban.schemas import CommentCreate, CommentRead
from agent_kanban.services import list_comments, post_comment

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
    session: AsyncSession = Depends(get_session),
):
    # UI posts as author "user" unless specified.
    if data.author == "":
        data.author = "user"
    return await post_comment(session, task_id, data.author, data.content)
