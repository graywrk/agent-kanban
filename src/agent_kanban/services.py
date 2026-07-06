"""Business logic shared by REST routes and MCP tools.

Authorization rule (spec §5.3): mutations require task.claimed_by == calling agent.
We raise PermissionError on violation so callers can map to HTTP 403 / MCP error.
"""
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from agent_kanban.events import event_bus
from agent_kanban.git import GitError, collect_diff, collect_diffstats, resolve_base_branch
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
    task.updated_at = datetime.now(UTC).replace(tzinfo=None)
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
            claimed_at=datetime.now(UTC).replace(tzinfo=None),
            updated_at=datetime.now(UTC).replace(tzinfo=None),
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
        # Copy so we can mutate; data.artifact is the agent-supplied dict.
        payload["artifact"] = dict(data.artifact)
        # Look up the most recent Artifact row for this task + path so the UI
        # can fetch the file via /api/artifacts/{id}/content. Never raises — a
        # select won't fail; if no row matches, the payload is left as-is and
        # the UI falls back to the file:/// path.
        art_path = data.artifact.get("path")
        if art_path:
            stmt = (
                select(Artifact)
                .where(Artifact.task_id == task_id, Artifact.path == art_path)
                .order_by(Artifact.id.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            row = result.scalars().first()
            if row is not None:
                payload["artifact"]["id"] = row.id
    blocked = False
    if data.kind.value == "status_change" and data.status:
        payload["status"] = data.status
        if data.status.get("to") == "blocked":
            task.status = TaskStatus.BLOCKED
            task.updated_at = datetime.now(UTC).replace(tzinfo=None)
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
    task.updated_at = datetime.now(UTC).replace(tzinfo=None)
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


async def _maybe_collect_review_diff(
    session: AsyncSession, task: Task, agent: str
) -> None:
    """Best-effort: if the task has repo_path + branch + a resolvable base,
    collect the diff and store it as a progress_event(kind=diff). On git
    failure, store a kind=error event so the user sees what went wrong.
    Never raises — review must succeed regardless of git.
    """
    if not task.repo_path or not task.branch:
        return
    base = await resolve_base_branch(session, task)
    if base is None:
        return
    try:
        diff_text = await collect_diff(task.repo_path, base, task.branch)
        diffstats = await collect_diffstats(task.repo_path, base, task.branch)
    except GitError as exc:
        session.add(
            ProgressEvent(
                task_id=task.id,
                agent=agent,
                kind="error",
                payload={"content": f"diff collection failed: {exc}"},
            )
        )
        return
    except Exception as exc:  # defensive: never break review on a git surprise
        session.add(
            ProgressEvent(
                task_id=task.id,
                agent=agent,
                kind="error",
                payload={"content": f"diff collection raised {type(exc).__name__}: {exc}"},
            )
        )
        return
    files = [s["path"] for s in diffstats]
    stats = {
        s["path"]: (
            f"+{s['added']} -{s['deleted']}" if s["added"] >= 0 and s["deleted"] >= 0
            else "binary"
        )
        for s in diffstats
    }
    session.add(
        ProgressEvent(
            task_id=task.id,
            agent=agent,
            kind="diff",
            payload={"content": diff_text, "files": files, "stats": stats},
        )
    )


async def request_review(
    session: AsyncSession, task_id: int, agent: str, summary: Optional[str] = None
) -> Task:
    task = await get_task(session, task_id)
    _check_claimer(task, agent)
    task.status = TaskStatus.REVIEW
    task.updated_at = datetime.now(UTC).replace(tzinfo=None)
    if summary:
        session.add(
            ProgressEvent(
                task_id=task_id,
                agent=agent,
                kind="text",
                payload={"content": summary},
            )
        )
    # Phase 3: best-effort diff auto-collection.
    await _maybe_collect_review_diff(session, task, agent)
    await session.commit()
    await session.refresh(task)
    await _publish_task_event("board", "task_review_requested", task)
    return task


async def set_task_branch(
    session: AsyncSession, task_id: int, agent: str, branch: str
) -> Task:
    task = await get_task(session, task_id)
    _check_claimer(task, agent)
    task.branch = branch
    task.updated_at = datetime.now(UTC).replace(tzinfo=None)
    await session.commit()
    await session.refresh(task)
    await _publish_task_event("board", "task_updated", task)
    return task


async def set_task_pr(
    session: AsyncSession,
    task_id: int,
    agent: str,
    pr_url: str,
    pr_status: str,
) -> Task:
    task = await get_task(session, task_id)
    _check_claimer(task, agent)
    task.pr_url = pr_url
    task.pr_status = pr_status
    task.updated_at = datetime.now(UTC).replace(tzinfo=None)
    await session.commit()
    await session.refresh(task)
    await _publish_task_event("board", "task_updated", task)
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


async def post_comment_with_status(
    session: AsyncSession,
    task_id: int,
    author: str,
    content: str,
    target_status: Optional[TaskStatus],
) -> Comment:
    """Post a comment and optionally transition the task status, atomically.

    Both the comment insert and the status update commit together. If the
    status update fails, the comment is not persisted either.
    """
    # Validate task exists.
    task = await get_task(session, task_id)
    # Insert comment (no commit yet).
    c = Comment(task_id=task_id, author=author, content=content)
    session.add(c)
    # Apply status transition if any.
    if target_status is not None:
        task.status = target_status
        task.updated_at = datetime.now(UTC).replace(tzinfo=None)
    # Single commit for both.
    await session.commit()
    await session.refresh(c)
    await event_bus.publish(
        f"task:{task_id}",
        {"type": "comment", "comment_id": c.id, "author": author},
    )
    if target_status is not None:
        await _publish_task_event("board", "task_updated", task)
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
