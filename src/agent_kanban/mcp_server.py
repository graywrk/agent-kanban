"""MCP server exposing the core tools for agents.

Uses FastMCP (bundled in the official `mcp` SDK since v1.2). The HTTP app
returned by `mcp.streamable_http_app()` is mounted in server.py at /mcp.

Two ways to obtain an instance:
  - `create_mcp()` factory: builds a fresh FastMCP with all core tools
    registered. Used by `server.create_app()` so each app gets its own session
    manager (StreamableHTTPSessionManager is single-use per instance; reusing
    one across multiple app lifespans raises RuntimeError).
  - `mcp` module-level singleton: a convenience instance for in-process tool
    invocation (e.g. `mcp.call_tool(name, args)`, used by tests). It does not
    serve HTTP and never has its session manager started.

Session resolution: each tool resolves the engine from current settings on
every call via `agent_kanban.db._engine_for(get_settings().database_url)` —
the same dynamic pattern the REST routes use (see `db.get_session`). A test
that overrides DATABASE_URL (and clears the settings cache) transparently
routes MCP tool calls to the throwaway DB; we intentionally avoid the
import-time-bound `AsyncSessionLocal`, which would stay pinned to the
production URL.
"""
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mcp.server.fastmcp import FastMCP

from agent_kanban.config import get_settings
from agent_kanban.db import _engine_for
from agent_kanban.models import ProgressKind, TaskStatus  # noqa: F401
from agent_kanban.schemas import ArtifactCreate, ProgressCreate
from agent_kanban.services import (
    claim_task as svc_claim_task,
    complete_task as svc_complete_task,
    get_next_task as svc_get_next_task,
    list_comments as svc_list_comments,
    list_tasks as svc_list_tasks,
    post_artifact as svc_post_artifact,
    post_comment as svc_post_comment,
    post_progress as svc_post_progress,
    request_review as svc_request_review,
    set_task_branch as svc_set_task_branch,
    set_task_pr as svc_set_task_pr,
)


@asynccontextmanager
async def session() -> AsyncIterator[AsyncSession]:
    """Yield an AsyncSession bound to the currently-configured DATABASE_URL.

    Mirrors `db.get_session` (used by the REST dependency) so MCP tools and
    HTTP routes share the same engine-resolution semantics and test isolation.
    """
    factory = async_sessionmaker(
        _engine_for(get_settings().database_url),
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with factory() as s:
        yield s


def _task_to_dict(task) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status.value if hasattr(task.status, "value") else task.status,
        "tags": task.tags,
        "claimed_by": task.claimed_by,
        "project_id": task.project_id,
        "branch": task.branch,
        "pr_url": task.pr_url,
        "pr_status": task.pr_status,
        "repo_path": task.repo_path,
        "base_branch": task.base_branch,
    }


def create_mcp() -> FastMCP:
    """Build a FastMCP instance with all core tools registered.

    Each call returns an independent instance with its own tool registry and
    (lazily-created, single-use) session manager. Callers that serve HTTP
    should create one instance per app so the session manager lifecycle is not
    shared across multiple app lifespans.
    """
    # `streamable_http_path="/"` makes the inner Starlette route resolve at "/"
    # so that mounting the app under "/mcp" in server.py yields a canonical
    # endpoint of "/mcp/" (with "/mcp" 307-redirecting to it). Without this the
    # inner default route "/mcp" would combine with the "/mcp" mount prefix to
    # produce a doubled "/mcp/mcp" path.
    mcp = FastMCP("agent-kanban", streamable_http_path="/")

    @mcp.tool()
    async def get_next_task(
        tags_any: Optional[list[str]] = None,
        tags_all: Optional[list[str]] = None,
        exclude_tags: Optional[list[str]] = None,
    ) -> Optional[dict]:
        """Return the next ready task (oldest first). Returns null if none.

        Filters:
          tags_any: task must have at least one of these tags
          tags_all: task must have all of these tags
          exclude_tags: task must have none of these tags

        Does NOT claim the task. Call claim_task to take it.
        """
        async with session() as s:
            task = await svc_get_next_task(s, tags_any, tags_all, exclude_tags)
            if task is None:
                return None
            return _task_to_dict(task)

    @mcp.tool()
    async def claim_task(task_id: int, agent: str) -> dict:
        """Atomically claim a ready task. Sets status to in_progress.

        Returns {ok: bool, reason: str?, task: Task?}.
        """
        async with session() as s:
            result = await svc_claim_task(s, task_id, agent)
            return {
                "ok": result.ok,
                "reason": result.reason,
                "task": _task_to_dict(result.task) if result.task else None,
            }

    @mcp.tool()
    async def list_tasks(
        status: Optional[str] = None, tags_any: Optional[list[str]] = None
    ) -> list[dict]:
        """List tasks, optionally filtered by status and/or tags. Does not claim."""
        status_enum = TaskStatus(status) if status else None
        async with session() as s:
            tasks = await svc_list_tasks(s, status_enum, tags_any)
            return [_task_to_dict(t) for t in tasks]

    @mcp.tool()
    async def post_progress(
        task_id: int,
        agent: str,
        kind: str,
        content: str,
        artifact: Optional[dict] = None,
        status: Optional[dict] = None,
    ) -> dict:
        """Append a progress event to the task's feed.

        kind: text | diff | artifact_ref | error | status_change
        content: text / raw diff / error message / status note
        artifact: {path, kind} required when kind == artifact_ref
        status: {from, to, note} required when kind == status_change

        Requires task.claimed_by == agent.
        """
        async with session() as s:
            ev = await svc_post_progress(
                s,
                task_id,
                ProgressCreate(
                    agent=agent,
                    kind=ProgressKind(kind),
                    content=content,
                    artifact=artifact,
                    status=status,
                ),
            )
            return {
                "id": ev.id,
                "kind": ev.kind.value if hasattr(ev.kind, "value") else ev.kind,
                "created_at": ev.created_at.isoformat(),
            }

    @mcp.tool()
    async def complete_task(
        task_id: int, agent: str, summary: Optional[str] = None
    ) -> dict:
        """Mark a task done. Requires task.claimed_by == agent."""
        async with session() as s:
            task = await svc_complete_task(s, task_id, agent, summary)
            return _task_to_dict(task)

    @mcp.tool()
    async def request_review(
        task_id: int, agent: str, summary: Optional[str] = None
    ) -> dict:
        """Mark a task ready for review. Requires task.claimed_by == agent."""
        async with session() as s:
            task = await svc_request_review(s, task_id, agent, summary)
            return _task_to_dict(task)

    @mcp.tool()
    async def get_comments(
        task_id: int, since_id: Optional[int] = None, agent: Optional[str] = None
    ) -> list[dict]:
        """List comments for a task since a given comment id.

        If agent is provided, marks the returned comments as seen by that agent
        (read receipt). Unseen comments are returned first.
        """
        async with session() as s:
            comments = await svc_list_comments(s, task_id, since_id, agent)
            return [
                {
                    "id": c.id,
                    "author": c.author,
                    "content": c.content,
                    "seen_by_agent": c.seen_by_agent,
                    "created_at": c.created_at.isoformat(),
                }
                for c in comments
            ]

    @mcp.tool()
    async def post_comment(task_id: int, agent: str, content: str) -> dict:
        """Post a comment authored by the calling agent."""
        async with session() as s:
            c = await svc_post_comment(s, task_id, agent, content)
            return {"id": c.id, "created_at": c.created_at.isoformat()}

    @mcp.tool()
    async def post_artifact(
        task_id: int,
        agent: str,
        kind: str,
        path: str,
        description: Optional[str] = None,
    ) -> dict:
        """Register an artifact file. Path must be inside an allow-listed root.

        Requires task.claimed_by == agent.
        """
        async with session() as s:
            art = await svc_post_artifact(
                s,
                task_id,
                ArtifactCreate(
                    agent=agent, kind=kind, path=path, description=description
                ),
            )
            return {"id": art.id, "path": art.path, "kind": art.kind}

    @mcp.tool()
    async def set_task_branch(task_id: int, agent: str, branch: str) -> dict:
        """Report the working branch the agent created for this task.

        Stores branch on the task so the UI can show it and request_review can
        collect a diff against the base branch. Requires task.claimed_by == agent.
        """
        async with session() as s:
            task = await svc_set_task_branch(s, task_id, agent, branch)
            return _task_to_dict(task)

    @mcp.tool()
    async def set_task_pr(
        task_id: int, agent: str, pr_url: str, status: str
    ) -> dict:
        """Report a pull request URL and its status for this task.

        status: "open" | "merged" | "closed". Requires task.claimed_by == agent.
        """
        async with session() as s:
            task = await svc_set_task_pr(s, task_id, agent, pr_url, status)
            return _task_to_dict(task)

    return mcp


# Module-level singleton for in-process tool invocation (tests, programmatic
# use). Not used for HTTP serving — server.create_app() builds its own instance
# via create_mcp() so the session manager lifecycle is not shared.
mcp = create_mcp()
