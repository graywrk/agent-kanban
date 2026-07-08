"""SQLModel ORM models matching spec §4.1."""
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Optional

from sqlalchemy import Enum as SAEnum
from sqlmodel import JSON, Column, Field, SQLModel


class TaskStatus(str, Enum):
    TODO = "todo"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class ProgressKind(str, Enum):
    TEXT = "text"
    DIFF = "diff"
    ARTIFACT_REF = "artifact_ref"
    ERROR = "error"
    STATUS_CHANGE = "status_change"


class Project(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    repo_path: Optional[str] = None
    default_branch: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))


class Task(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: Optional[int] = Field(default=None, foreign_key="project.id")
    title: str
    description: str = ""
    status: TaskStatus = Field(
        default=TaskStatus.TODO,
        sa_column=Column(
            SAEnum(
                TaskStatus,
                name="taskstatus",
                values_callable=lambda e: [m.value for m in e],
            ),
            index=True,
        ),
    )
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    claimed_by: Optional[str] = Field(default=None, index=True)
    claimed_at: Optional[datetime] = None
    # Hard assignment: an operator reserves a task for a specific agent. The
    # task is then visible (in get_next_task / list_tasks) and claimable only by
    # that agent. Other agents don't see it. Set/cleared via REST PATCH by a
    # human operator — agents themselves cannot assign.
    assigned_to: Optional[str] = Field(default=None, index=True)
    sort_order: float = Field(default=0.0)
    # Phase 3 fields (present now so migrations are stable; unused in Phase 1)
    repo_path: Optional[str] = None
    base_branch: Optional[str] = None
    branch: Optional[str] = None
    pr_url: Optional[str] = None
    pr_status: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))


class ProgressEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="task.id", index=True)
    agent: str
    kind: ProgressKind = Field(
        sa_column=Column(
            SAEnum(
                ProgressKind,
                name="progresskind",
                values_callable=lambda e: [m.value for m in e],
            )
        )
    )
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None), index=True)


class Comment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="task.id", index=True)
    author: str
    content: str
    seen_by_agent: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None), index=True)


class Artifact(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="task.id", index=True)
    path: str
    kind: str
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    password_hash: str
    is_admin: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))


class Token(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    agent_name: str = Field(index=True)
    token_hash: str  # bcrypt hash of the opaque token
    token_prefix: str = Field(default="", index=True)  # first 8 chars of plaintext, for fast lookup
    description: Optional[str] = None
    created_by_user_id: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
    last_used_at: Optional[datetime] = None
