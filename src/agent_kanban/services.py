"""Business logic shared by REST routes and MCP tools.

Authorization rule (spec §5.3): mutations require task.claimed_by == calling agent.
We raise PermissionError on violation so callers can map to HTTP 403 / MCP error.
"""
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from agent_kanban.events import event_bus
from agent_kanban.models import (
    Artifact,
    Comment,
    ProgressEvent,
    Task,
    TaskStatus,
)
from agent_kanban.schemas import (
    ArtifactCreate,
    ClaimResult,
    ProgressCreate,
    TaskCreate,
    TaskRead,
    TaskUpdate,
)


def _to_task_read(task: Task) -> TaskRead:
    # ClaimResult.task is typed TaskRead; bridge ORM -> schema explicitly.
    return TaskRead.model_validate(task, from_attributes=True)


def _check_claimer(task: Task, agent: str) -> None:
    if task.claimed_by != agent:
        raise PermissionError(
            f"task {task.id} is claimed by {task.claimed_by!r}, not {agent!r}"
        )


def _is_path_allowed(path: str, allowed_roots: list[str]) -> bool:
    p = Path(path).expanduser().resolve()
    for root in allowed_roots:
        try:
            p.relative_to(Path(root).expanduser().resolve())
            return True
        except ValueError:
            continue
    return False


async def _publish_task_event(channel: str, evt_type: str, task: Task) -> None:
    payload = {
        "type": evt_type,
        "task_id": task.id,
        "status": task.status.value if isinstance(task.status, TaskStatus) else task.status,
    }
    await event_bus.publish(channel, payload)
    await event_bus.publish(f"task:{task.id}", payload)


# ---- Task CRUD ----
async def create_task(session: AsyncSession, data: TaskCreate) -> Task:
    task = Task(**data.model_dump())
    session.add(task)
    await session.commit()
    await session.refresh(task)
    await _publish_task_event("board", "task_created", task)
    return task


async def update_task(session: AsyncSession, task_id: int, data: TaskUpdate) -> Task:
    task = await session.get(Task, task_id)
    if task is None:
        raise ValueError(f"task {task_id} not found")
    changes = data.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(task, k, v)
    task.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(task)
    await _publish_task_event("board", "task_updated", task)
    return task


async def list_tasks(
    session: AsyncSession,
    status: Optional[TaskStatus] = None,
    tags_any: Optional[list[str]] = None,
) -> list[Task]:
    stmt = select(Task).order_by(Task.sort_order, Task.created_at)
    if status is not None:
        stmt = stmt.where(Task.status == status)
    result = await session.execute(stmt)
    tasks = result.scalars().all()
    if tags_any:
        tasks = [t for t in tasks if any(tag in t.tags for tag in tags_any)]
    return list(tasks)


async def get_task(session: AsyncSession, task_id: int) -> Task:
    task = await session.get(Task, task_id)
    if task is None:
        raise ValueError(f"task {task_id} not found")
    return task


async def get_next_task(
    session: AsyncSession,
    tags_any: Optional[list[str]],
    tags_all: Optional[list[str]],
    exclude_tags: Optional[list[str]],
) -> Optional[Task]:
    stmt = (
        select(Task)
        .where(Task.status == TaskStatus.READY)
        .order_by(Task.sort_order, Task.created_at)
    )
    result = await session.execute(stmt)
    for task in result.scalars():
        if tags_any and not any(t in task.tags for t in tags_any):
            continue
        if tags_all and not all(t in task.tags for t in tags_all):
            continue
        if exclude_tags and any(t in task.tags for t in exclude_tags):
            continue
        return task
    return None


# ---- Claiming ----
async def claim_task(session: AsyncSession, task_id: int, agent: str) -> ClaimResult:
    # Atomic conditional update: only flips if status is still READY.
    stmt = (
        update(Task)
        .where(Task.id == task_id, Task.status == TaskStatus.READY)
        .values(
            status=TaskStatus.IN_PROGRESS,
            claimed_by=agent,
            claimed_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        .returning(Task.id)
    )
    result = await session.execute(stmt)
    row = result.first()
    if row is None:
        # Either doesn't exist or no longer READY.
        task = await session.get(Task, task_id)
        if task is None:
            return ClaimResult(ok=False, reason="task not found")
        return ClaimResult(
            ok=False,
            reason=f"task is {task.status.value}, not ready",
            task=None,
        )
    await session.commit()
    task = await session.get(Task, task_id)
    assert task is not None
    await _publish_task_event("board", "task_claimed", task)
    return ClaimResult(ok=True, task=_to_task_read(task))


# ---- Progress ----
async def post_progress(
    session: AsyncSession, task_id: int, data: ProgressCreate
) -> ProgressEvent:
    task = await get_task(session, task_id)
    _check_claimer(task, data.agent)
    payload: dict = {"content": data.content}
    if data.kind.value == "artifact_ref" and data.artifact:
        payload["artifact"] = data.artifact
    blocked = False
    if data.kind.value == "status_change" and data.status:
        payload["status"] = data.status
        if data.status.get("to") == "blocked":
            task.status = TaskStatus.BLOCKED
            task.updated_at = datetime.utcnow()
            blocked = True
    ev = ProgressEvent(
        task_id=task_id,
        agent=data.agent,
        kind=data.kind,
        payload=payload,
    )
    session.add(ev)
    await session.commit()
    await session.refresh(ev)
    if blocked:
        # Lifecycle event fans out to the board channel AND task:{id}. Skip the
        # redundant task-channel "progress" publish below so subscribers see a
        # single authoritative "task_blocked" event for this transition.
        await session.refresh(task)
        await _publish_task_event("board", "task_blocked", task)
        return ev
    await event_bus.publish(
        f"task:{task_id}",
        {"type": "progress", "event_id": ev.id, "kind": ev.kind.value},
    )
    return ev


async def complete_task(
    session: AsyncSession, task_id: int, agent: str, summary: Optional[str] = None
) -> Task:
    task = await get_task(session, task_id)
    _check_claimer(task, agent)
    task.status = TaskStatus.DONE
    task.updated_at = datetime.utcnow()
    if summary:
        session.add(
            ProgressEvent(
                task_id=task_id,
                agent=agent,
                kind="text",
                payload={"content": summary},
            )
        )
    await session.commit()
    await session.refresh(task)
    await _publish_task_event("board", "task_completed", task)
    return task


async def request_review(
    session: AsyncSession, task_id: int, agent: str, summary: Optional[str] = None
) -> Task:
    task = await get_task(session, task_id)
    _check_claimer(task, agent)
    task.status = TaskStatus.REVIEW
    task.updated_at = datetime.utcnow()
    if summary:
        session.add(
            ProgressEvent(
                task_id=task_id,
                agent=agent,
                kind="text",
                payload={"content": summary},
            )
        )
    await session.commit()
    await session.refresh(task)
    await _publish_task_event("board", "task_review_requested", task)
    return task


# ---- Comments ----
async def list_comments(
    session: AsyncSession,
    task_id: int,
    since_id: Optional[int],
    mark_seen_by: Optional[str],
) -> list[Comment]:
    stmt = select(Comment).where(Comment.task_id == task_id)
    if since_id is not None:
        stmt = stmt.where(Comment.id > since_id)
    # Unseen first.
    stmt = stmt.order_by(Comment.seen_by_agent.asc(), Comment.id.asc())
    result = await session.execute(stmt)
    comments = list(result.scalars())
    if mark_seen_by is not None:
        # seen_by_agent is a read-receipt for messages TO the agent. The reading
        # agent should not mark its own comments as "seen by itself" — they were
        # authored by it, never "unseen" from its perspective.
        for c in comments:
            if not c.seen_by_agent and c.author != mark_seen_by:
                c.seen_by_agent = True
        await session.commit()
    return comments


async def post_comment(
    session: AsyncSession, task_id: int, author: str, content: str
) -> Comment:
    c = Comment(task_id=task_id, author=author, content=content)
    session.add(c)
    await session.commit()
    await session.refresh(c)
    await event_bus.publish(
        f"task:{task_id}",
        {"type": "comment", "comment_id": c.id, "author": author},
    )
    return c


# ---- Artifacts ----
async def post_artifact(
    session: AsyncSession, task_id: int, data: ArtifactCreate
) -> Artifact:
    task = await get_task(session, task_id)
    _check_claimer(task, data.agent)
    allowed_roots = [
        Path.home() / ".agent-kanban" / "artifacts" / str(task_id),
    ]
    if task.repo_path:
        allowed_roots.append(task.repo_path)
    if not _is_path_allowed(data.path, [str(r) for r in allowed_roots]):
        raise ValueError(
            f"artifact path {data.path!r} is not inside an allowed root"
        )
    # NOTE: ArtifactCreate carries `agent` for authorization, but the Artifact
    # table has no agent column — drop it before constructing the ORM object.
    art = Artifact(task_id=task_id, **data.model_dump(exclude={"agent"}))
    session.add(art)
    await session.commit()
    await session.refresh(art)
    return art
