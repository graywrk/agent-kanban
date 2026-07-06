"""REST routes for tasks (used by the UI)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from agent_kanban.db import get_session
from agent_kanban.models import TaskStatus
from agent_kanban.schemas import TaskCreate, TaskRead, TaskUpdate
from agent_kanban.services import create_task, get_task, list_tasks, update_task

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskRead])
async def get_tasks(
    status: Optional[str] = None,
    tags_any: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    status_enum = TaskStatus(status) if status else None
    tags = tags_any.split(",") if tags_any else None
    return await list_tasks(session, status_enum, tags)


@router.post("", response_model=TaskRead, status_code=201)
async def post_task(data: TaskCreate, session: AsyncSession = Depends(get_session)):
    return await create_task(session, data)


@router.get("/{task_id}", response_model=TaskRead)
async def get_one(task_id: int, session: AsyncSession = Depends(get_session)):
    try:
        return await get_task(session, task_id)
    except ValueError:
        raise HTTPException(404, "task not found")


@router.patch("/{task_id}", response_model=TaskRead)
async def patch_task(
    task_id: int, data: TaskUpdate, session: AsyncSession = Depends(get_session)
):
    try:
        return await update_task(session, task_id, data)
    except ValueError:
        raise HTTPException(404, "task not found")
