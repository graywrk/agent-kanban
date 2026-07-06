"""Git helpers for diff collection (Phase 3).

The board never creates branches/worktrees/PRs. This module only READS from
git repositories that agents work in, to render review diffs in the UI.
"""
import asyncio
from pathlib import Path
from typing import Union


class GitError(RuntimeError):
    """Raised when a git operation fails (non-zero exit, timeout, bad path)."""


async def collect_diff(
    repo_path: Union[str, Path],
    base: str,
    head: str,
    timeout_s: float = 10.0,
) -> str:
    """Return the unified diff between <base> and <head> in repo_path.

    Returns "" if there are no changes. Raises GitError on non-zero exit,
    timeout, or if repo_path does not exist.
    """
    repo = Path(repo_path)
    if not repo.is_dir():
        raise GitError(f"repo path does not exist or is not a directory: {repo}")

    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            str(repo),
            "diff",
            f"{base}...{head}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise GitError("git executable not found on PATH") from exc

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise GitError(f"git diff timed out after {timeout_s}s")

    if proc.returncode != 0:
        msg = stderr.decode(errors="replace").strip() or f"exit code {proc.returncode}"
        raise GitError(f"git diff failed: {msg}")

    return stdout.decode(errors="replace")


async def resolve_base_branch(session, task) -> "str | None":
    """Resolve the diff base for a task.

    Order: task.base_branch → project.default_branch → None.
    Reads the project if the task has a project_id.
    """
    if task.base_branch:
        return task.base_branch
    if task.project_id:
        from agent_kanban.models import Project
        project = await session.get(Project, task.project_id)
        if project and project.default_branch:
            return project.default_branch
    return None
