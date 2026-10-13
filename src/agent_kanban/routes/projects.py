"""REST routes for projects."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from agent_kanban.auth import Principal, get_current_principal
from agent_kanban.db import get_session
from agent_kanban.models import Project
from agent_kanban.schemas import ProjectCreate, ProjectRead, ProjectUpdate
from agent_kanban.services import create_project, list_projects, update_project

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectRead])
async def get_projects(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    return await list_projects(session)


@router.post("", response_model=ProjectRead, status_code=201)
async def post_project(
    data: ProjectCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    return await create_project(session, data)


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(
    project_id: int,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectRead)
async def patch_project(
    project_id: int,
    data: ProjectUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    try:
        return await update_project(session, project_id, data)
    except ValueError:
        raise HTTPException(404, "project not found")
