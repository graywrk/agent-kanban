"""Pydantic schemas for the API surface (REST + MCP)."""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from agent_kanban.models import ProgressKind, TaskStatus


class ReadBase(BaseModel):
    """Base for response models built from ORM objects.

    Routes return ORM instances and let FastAPI serialize via
    `response_model=...Read`; that path calls `model_validate(orm_obj)`,
    which requires `from_attributes=True`.
    """

    model_config = ConfigDict(from_attributes=True)


# ---- Project ----
class ProjectCreate(BaseModel):
    name: str
    repo_path: Optional[str] = None
    default_branch: Optional[str] = None


class ProjectRead(ReadBase):
    id: int
    name: str
    repo_path: Optional[str] = None
    default_branch: Optional[str] = None
    created_at: datetime


# ---- Task ----
class TaskCreate(BaseModel):
    title: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    project_id: Optional[int] = None
    status: TaskStatus = TaskStatus.TODO
    sort_order: float = 0.0
    repo_path: Optional[str] = None
    base_branch: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None
    status: Optional[TaskStatus] = None
    sort_order: Optional[float] = None
    project_id: Optional[int] = None
    branch: Optional[str] = None
    pr_url: Optional[str] = None
    pr_status: Optional[str] = None
    repo_path: Optional[str] = None
    base_branch: Optional[str] = None


class TaskRead(ReadBase):
    id: int
    project_id: Optional[int] = None
    title: str
    description: str
    status: TaskStatus
    tags: list[str]
    claimed_by: Optional[str] = None
    claimed_at: Optional[datetime] = None
    sort_order: float
    repo_path: Optional[str] = None
    base_branch: Optional[str] = None
    branch: Optional[str] = None
    pr_url: Optional[str] = None
    pr_status: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ---- Progress ----
class ProgressCreate(BaseModel):
    agent: str
    kind: ProgressKind
    content: str
    artifact: Optional[dict[str, str]] = None
    status: Optional[dict[str, Any]] = None  # {from, to, note}


class ProgressRead(ReadBase):
    id: int
    task_id: int
    agent: str
    kind: ProgressKind
    payload: dict[str, Any]
    created_at: datetime


# ---- Comment ----
class CommentCreate(BaseModel):
    author: str
    content: str


class CommentRead(ReadBase):
    id: int
    task_id: int
    author: str
    content: str
    seen_by_agent: bool
    created_at: datetime


# ---- Artifact ----
class ArtifactCreate(BaseModel):
    agent: str
    kind: str
    path: str
    description: Optional[str] = None


class ArtifactRead(ReadBase):
    id: int
    task_id: int
    path: str
    kind: str
    description: Optional[str] = None
    created_at: datetime


# ---- Claim result (used by MCP claim_task) ----
class ClaimResult(BaseModel):
    ok: bool
    reason: Optional[str] = None
    task: Optional[TaskRead] = None
