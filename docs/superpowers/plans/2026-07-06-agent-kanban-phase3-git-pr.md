# Agent Kanban — Phase 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional git/PR integration so coding tasks can record their working branch, report PRs, and auto-collect a review diff — without the board ever creating worktrees, branches, or PRs itself.

**Architecture:** Three additive pieces on top of the existing services layer: (1) two new MCP tools (`set_task_branch`, `set_task_pr`) that let agents report what they did; (2) a `git.collect_diff` helper invoked from `request_review` that runs `git -C <repo> diff` once and stores it as a `progress_event(kind=diff)`; (3) UI badges + a branch/PR field in the New Task modal so the user can configure coding tasks. The board stays passive — agents and the user drive all git operations; the board only records and renders.

**Tech Stack:** Python 3.11 + FastAPI + sqlmodel (existing); `subprocess` for git CLI (no new deps); React/Vite/TS for UI badges (existing). No new dependencies, no DB migrations (all Phase 3 columns already exist from Phase 1).

**Spec:** `docs/superpowers/specs/2026-07-05-agent-kanban-design.md` §6 (Git / PR integration). Phase 3 fields (`repo_path`, `base_branch`, `branch`, `pr_url`, `pr_status`) are already on the `Task` model since Phase 1; this plan wires them up.

## Global Constraints

- All Phase 1+2 constraints still apply (Python 3.11+, PostgreSQL on host port **5436**, MCP SDK `mcp>=1.27,<2.0`, no auth, default port 7331).
- **No DB migrations.** The `repo_path`, `base_branch`, `branch`, `pr_url`, `pr_status` columns exist since Phase 1. This plan only adds code that reads/writes them.
- **No new dependencies.** Git operations use the `git` CLI via `subprocess` (`asyncio.create_subprocess_exec`). No `pygit2` or `GitPython`.
- The board **never** creates worktrees, branches, commits, or PRs. It records what agents/users report and collects diffs for display.
- Authorization unchanged: every mutation still requires `claimed_by == agent`. The new `set_task_branch` and `set_task_pr` MCP tools follow this rule.
- Git operations must be **timeout-bounded** (default 10s) so a hung `git` process cannot stall the request handler.
- Diff auto-collection is **best-effort**: if `repo_path`/`base_branch`/`branch` are missing or `git diff` fails, the request still succeeds and a warning is logged; no diff event is stored.
- The diff is refreshed every time the task re-enters `review` (not just the first time), per spec §6.2.

---

## File Structure

Phase 3 touches existing files only. No new modules; no new deps.

```
src/agent_kanban/
├── git.py               # REWRITE: real collect_diff via subprocess + timeout; resolve_base_branch helper
├── services.py          # MODIFY: request_review triggers diff auto-collection; add set_branch/set_pr service fns
├── schemas.py           # MODIFY: add repo_path/base_branch to TaskCreate; TaskUpdate gains branch/pr fields
├── mcp_server.py        # MODIFY: register set_task_branch + set_task_pr tools (Phase 3)
├── routes/
│   └── tasks.py         # (no change — TaskCreate/TaskUpdate schema changes flow through automatically)
tests/
├── test_git.py          # CREATE: collect_diff against a temp git repo; timeout behavior
├── test_services.py     # MODIFY: request_review triggers diff collection (mocked git)
└── test_mcp_server.py   # MODIFY: set_task_branch + set_task_pr behavior + authz
web/src/
├── components/
│   └── TaskCard.tsx     # MODIFY: branch/PR badges in card
├── pages/
│   ├── Board.tsx        # (no change)
│   └── CardDetail.tsx   # MODIFY: branch/PR badges in detail header
│   └── NewTaskModal (Component)  # MODIFY: optional repo_path + base_branch fields
└── types.ts             # MODIFY: Task type already has the fields (verify); no change expected
```

**Decomposition rationale:** Task 1 (git helper) is independently testable with a temp repo and is the foundation. Task 2 (services + schemas) builds on it and adds the agent-facing service functions. Task 3 (MCP tools) exposes Task 2's service functions to agents. Task 4 (UI badges + modal fields) consumes the already-existing model fields. Each task ends green and committable.

---

## Task 1: `git.collect_diff` helper (real implementation)

Replace the Phase 1 stub with a real subprocess-based diff collector, plus a base-branch resolver.

**Files:**
- Rewrite: `src/agent_kanban/git.py`
- Create: `tests/test_git.py`

**Interfaces:**
- Consumes: none (pure subprocess + path handling)
- Produces:
  - `async def collect_diff(repo_path: str | Path, base: str, head: str, timeout_s: float = 10.0) -> str` — returns the unified diff text. Raises `GitError` (a new exception) on non-zero exit or timeout. Returns empty string `""` if there are no changes (exit 0, empty stdout).
  - `async def resolve_base_branch(session, task) -> str | None` — returns `task.base_branch` → else the task's project's `default_branch` → else `None`. Used by `request_review` to decide whether to collect a diff.
  - `class GitError(RuntimeError)` — exception type for git failures (bad repo, missing ref, timeout).

- [ ] **Step 1: Write failing tests in `tests/test_git.py`**

Create `tests/test_git.py`:
```python
"""Tests for git.collect_diff against a real temp git repo."""
import os
import tempfile
from pathlib import Path

import pytest

from agent_kanban.git import GitError, collect_diff


def _run(cmd: list[str], cwd: Path) -> None:
    import subprocess
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def tmp_repo():
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d)
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        _run(["git", "init", "-q", "-b", "main"], repo)
        # Make git happy without global identity.
        for k, v in env.items():
            _run(["git", "config", k.replace("_", ".", 1).lower(), v], repo) if k.startswith("GIT_") else None
        (repo / "README.md").write_text("# hello\n")
        _run(["git", "add", "."], repo)
        _run(["git", "commit", "-q", "-m", "init"], repo)
        # Create a feature branch with a change.
        _run(["git", "checkout", "-q", "-b", "feat"], repo)
        (repo / "README.md").write_text("# hello world\n")
        _run(["git", "add", "."], repo)
        _run(["git", "commit", "-q", "-m", "expand greeting"], repo)
        yield repo


@pytest.mark.asyncio
async def test_collect_diff_returns_unified_diff(tmp_repo):
    diff = await collect_diff(tmp_repo, "main", "feat")
    assert "README.md" in diff
    assert "+# hello world" in diff
    assert "-# hello" in diff


@pytest.mark.asyncio
async def test_collect_diff_empty_when_no_changes(tmp_repo):
    # main vs main → no diff
    diff = await collect_diff(tmp_repo, "main", "main")
    assert diff == ""


@pytest.mark.asyncio
async def test_collect_diff_raises_on_bad_repo(tmp_repo):
    with pytest.raises(GitError):
        await collect_diff(tmp_repo, "main", "nonexistent-branch")


@pytest.mark.asyncio
async def test_collect_diff_raises_on_missing_path(tmp_path):
    with pytest.raises(GitError):
        await collect_diff(tmp_path / "does-not-exist", "main", "feat")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_git.py -v`
Expected: FAIL with `ImportError` (the stub `collect_diff` raises `NotImplementedError`, but more importantly `GitError` doesn't exist yet).

- [ ] **Step 3: Implement `git.py`**

Replace the entire contents of `src/agent_kanban/git.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_git.py -v`
Expected: PASS (4 tests). If the temp-repo fixture has trouble with git identity in CI, the env vars in the fixture should cover it; if not, add `git config user.email/user.name` calls inside `_run`.

- [ ] **Step 5: Run the full suite to confirm no regression**

Run: `uv run pytest -v`
Expected: 47 prior + 4 new = 51 passing.

- [ ] **Step 6: Commit**

```bash
git add src/agent_kanban/git.py tests/test_git.py
git commit -m "feat(git): real collect_diff via subprocess with timeout; resolve_base_branch"
```

---

## Task 2: `set_branch` / `set_pr` services + diff auto-collection on review

Wire git into the services layer: `set_task_branch` and `set_task_pr` service functions (with authorization), and modify `request_review` to invoke `collect_diff` when a base+branch are resolvable.

**Files:**
- Modify: `src/agent_kanban/services.py`
- Modify: `src/agent_kanban/schemas.py`
- Modify: `tests/test_services.py`

**Interfaces:**
- Consumes: `agent_kanban.git.{collect_diff, resolve_base_branch, GitError}`, existing services
- Produces:
  - `async def set_task_branch(session, task_id, agent, branch) -> Task` — sets `task.branch`, requires claimer.
  - `async def set_task_pr(session, task_id, agent, pr_url, pr_status) -> Task` — sets `task.pr_url`/`pr_status`, requires claimer.
  - Modified `request_review(session, task_id, agent, summary)` — after the status flip to REVIEW, if `resolve_base_branch` returns non-None AND `task.branch` is set AND `task.repo_path` is set, calls `collect_diff` and stores the result as a `progress_event(kind="diff", payload={"content": diff, "files": [...], "stats": {...}})`. On `GitError`, logs a warning and stores a `kind="error"` progress event instead (so the user sees something went wrong with diff collection). Catches all exceptions so the review request itself never fails due to git.

**Schemas (TaskCreate / TaskUpdate) additions:**
- `TaskCreate` gains `repo_path: Optional[str] = None` and `base_branch: Optional[str] = None` (so the UI can configure a coding task at creation).
- `TaskUpdate` gains `branch: Optional[str] = None`, `pr_url: Optional[str] = None`, `pr_status: Optional[str] = None`, `repo_path: Optional[str] = None`, `base_branch: Optional[str] = None`. (The MCP tools will use the service functions, not TaskUpdate, but having the fields lets the UI PATCH them if needed.)

- [ ] **Step 1: Write failing tests in `tests/test_services.py`**

Append to `tests/test_services.py`:
```python
import pytest
from unittest.mock import AsyncMock, patch

from agent_kanban.git import GitError
from agent_kanban.models import TaskStatus
from agent_kanban.schemas import ProgressCreate, TaskCreate
from agent_kanban.services import (
    claim_task,
    create_task,
    request_review,
    set_task_branch,
    set_task_pr,
)


@pytest.mark.asyncio
async def test_set_task_branch_requires_claimer(session):
    t = await create_task(session, TaskCreate(title="t", status=TaskStatus.READY))
    await claim_task(session, t.id, "codex")
    with pytest.raises(PermissionError):
        await set_task_branch(session, t.id, "hermes", "feat/x")


@pytest.mark.asyncio
async def test_set_task_branch_sets_branch(session):
    t = await create_task(session, TaskCreate(title="t", status=TaskStatus.READY))
    await claim_task(session, t.id, "codex")
    out = await set_task_branch(session, t.id, "codex", "feat/dark-mode")
    assert out.branch == "feat/dark-mode"


@pytest.mark.asyncio
async def test_set_task_pr_requires_claimer(session):
    t = await create_task(session, TaskCreate(title="t", status=TaskStatus.READY))
    await claim_task(session, t.id, "codex")
    with pytest.raises(PermissionError):
        await set_task_pr(session, t.id, "hermes", "https://github.com/x/y/pull/1", "open")


@pytest.mark.asyncio
async def test_set_task_pr_sets_url_and_status(session):
    t = await create_task(session, TaskCreate(title="t", status=TaskStatus.READY))
    await claim_task(session, t.id, "codex")
    out = await set_task_pr(
        session, t.id, "codex", "https://github.com/x/y/pull/1", "open"
    )
    assert out.pr_url == "https://github.com/x/y/pull/1"
    assert out.pr_status == "open"


@pytest.mark.asyncio
async def test_request_review_collects_diff_when_configured(session):
    t = await create_task(
        session,
        TaskCreate(
            title="t",
            status=TaskStatus.READY,
            repo_path="/tmp/fakerepo",
            base_branch="main",
        ),
    )
    await claim_task(session, t.id, "codex")
    await set_task_branch(session, t.id, "codex", "feat/x")

    fake_diff = "--- a/f.txt\n+++ b/f.txt\n@@ -1 +1 @@\n-old\n+new\n"
    with patch("agent_kanban.services.collect_diff", new=AsyncMock(return_value=fake_diff)):
        await request_review(session, t.id, "codex", summary="review please")

    from sqlmodel import select
    from agent_kanban.models import ProgressEvent
    stmt = select(ProgressEvent).where(ProgressEvent.task_id == t.id)
    result = await session.execute(stmt)
    events = list(result.scalars())
    diff_events = [e for e in events if e.kind.value == "diff"]
    assert len(diff_events) == 1
    assert "old" in diff_events[0].payload["content"]
    assert "new" in diff_events[0].payload["content"]


@pytest.mark.asyncio
async def test_request_review_skips_diff_without_repo_path(session):
    t = await create_task(session, TaskCreate(title="t", status=TaskStatus.READY))
    await claim_task(session, t.id, "codex")

    with patch("agent_kanban.services.collect_diff", new=AsyncMock()) as mock_diff:
        await request_review(session, t.id, "codex", summary="review please")
        mock_diff.assert_not_called()


@pytest.mark.asyncio
async def test_request_review_records_error_event_on_git_failure(session):
    t = await create_task(
        session,
        TaskCreate(
            title="t",
            status=TaskStatus.READY,
            repo_path="/tmp/fakerepo",
            base_branch="main",
        ),
    )
    await claim_task(session, t.id, "codex")
    await set_task_branch(session, t.id, "codex", "feat/x")

    with patch(
        "agent_kanban.services.collect_diff",
        new=AsyncMock(side_effect=GitError("boom")),
    ):
        await request_review(session, t.id, "codex", summary="review please")

    from sqlmodel import select
    from agent_kanban.models import ProgressEvent
    stmt = select(ProgressEvent).where(ProgressEvent.task_id == t.id)
    result = await session.execute(stmt)
    events = list(result.scalars())
    error_events = [e for e in events if e.kind.value == "error"]
    assert len(error_events) == 1
    assert "boom" in error_events[0].payload["content"]
    # Status still moved to review despite the git failure.
    from agent_kanban.services import get_task
    refreshed = await get_task(session, t.id)
    assert refreshed.status == TaskStatus.REVIEW
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_services.py -v`
Expected: FAIL — `set_task_branch` and `set_task_pr` don't exist; `request_review` doesn't collect a diff.

- [ ] **Step 3: Add schema fields**

Open `src/agent_kanban/schemas.py`. In `TaskCreate`, add two fields (after `sort_order`):
```python
    repo_path: Optional[str] = None
    base_branch: Optional[str] = None
```

In `TaskUpdate`, add five fields (after `project_id`):
```python
    branch: Optional[str] = None
    pr_url: Optional[str] = None
    pr_status: Optional[str] = None
    repo_path: Optional[str] = None
    base_branch: Optional[str] = None
```

(`Optional` is already imported in schemas.py from Phase 1.)

- [ ] **Step 4: Implement service functions and modify `request_review`**

Open `src/agent_kanban/services.py`.

a) Add the git import near the top imports:
```python
from agent_kanban.git import GitError, collect_diff, resolve_base_branch
```

b) Add the two new service functions (place them after `request_review` or near `claim_task` — anywhere in the file is fine, but grouping with the other task-mutation functions is cleanest):
```python
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
```

c) Modify `request_review` to collect a diff after the status flip. Find the existing `request_review` function. After the existing `if summary:` block and BEFORE the final `await session.commit()`, insert the diff-collection logic. The modified `request_review` should look like:
```python
async def request_review(
    session: AsyncSession, task_id: int, agent: str, summary: Optional[str]
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
```

And add the helper `_maybe_collect_review_diff` just above `request_review`:
```python
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
    files = _extract_diff_filenames(diff_text)
    session.add(
        ProgressEvent(
            task_id=task.id,
            agent=agent,
            kind="diff",
            payload={"content": diff_text, "files": files, "stats": {}},
        )
    )


def _extract_diff_filenames(diff_text: str) -> list[str]:
    """Pull affected file paths from a unified diff (best-effort)."""
    import re
    return list(dict.fromkeys(re.findall(r"^\+\+\+ b/(.+)$", diff_text, flags=re.MULTILINE)))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_services.py -v`
Expected: PASS (all prior + 7 new). If `test_request_review_collects_diff_when_configured` fails because the diff event's `kind` is stored as the enum, adjust the assertion to compare against `ProgressKind.DIFF` or use `.value` consistently.

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -v`
Expected: 51 prior + 7 new = 58 passing.

- [ ] **Step 7: Commit**

```bash
git add src/agent_kanban/services.py src/agent_kanban/schemas.py tests/test_services.py
git commit -m "feat(services): set_task_branch/set_task_pr + diff auto-collection on review"
```

---

## Task 3: MCP tools `set_task_branch` and `set_task_pr`

Expose the two new service functions as MCP tools so agents can report their branch and PR.

**Files:**
- Modify: `src/agent_kanban/mcp_server.py`
- Modify: `tests/test_mcp_server.py`

**Interfaces:**
- Consumes: `agent_kanban.services.{set_task_branch, set_task_pr}`
- Produces: two new MCP tools registered on the FastMCP instance:
  - `set_task_branch(task_id: int, agent: str, branch: str) -> dict` — returns the updated task fields.
  - `set_task_pr(task_id: int, agent: str, pr_url: str, status: str) -> dict` — returns the updated task fields.

- [ ] **Step 1: Write failing tests in `tests/test_mcp_server.py`**

Append to `tests/test_mcp_server.py` (mirror the existing test style there — it uses `mcp.call_tool` and a `_to_dict` helper):
```python
@pytest.mark.asyncio
async def test_set_task_branch_via_mcp(db_url):
    from agent_kanban.db import AsyncSessionLocal
    from agent_kanban.mcp_server import mcp
    from agent_kanban.services import create_task, update_task
    from agent_kanban.models import TaskStatus
    from agent_kanban.schemas import TaskCreate
    async with AsyncSessionLocal() as session:
        t = await create_task(session, TaskCreate(title="t", status=TaskStatus.READY))
        task_id = t.id
        await session.close()
    await mcp.call_tool("claim_task", {"task_id": task_id, "agent": "codex"})
    result = await mcp.call_tool(
        "set_task_branch", {"task_id": task_id, "agent": "codex", "branch": "feat/x"}
    )
    data = _to_dict(result)
    flat = data if isinstance(data, dict) and "branch" in data else data.get("result", data)
    assert flat["branch"] == "feat/x"


@pytest.mark.asyncio
async def test_set_task_branch_rejects_non_claimer(db_url):
    from agent_kanban.db import AsyncSessionLocal
    from agent_kanban.mcp_server import mcp
    from agent_kanban.services import create_task
    from agent_kanban.models import TaskStatus
    from agent_kanban.schemas import TaskCreate
    async with AsyncSessionLocal() as session:
        t = await create_task(session, TaskCreate(title="t", status=TaskStatus.READY))
        task_id = t.id
        await session.close()
    await mcp.call_tool("claim_task", {"task_id": task_id, "agent": "codex"})
    with pytest.raises(Exception):
        await mcp.call_tool(
            "set_task_branch",
            {"task_id": task_id, "agent": "hermes", "branch": "feat/y"},
        )


@pytest.mark.asyncio
async def test_set_task_pr_via_mcp(db_url):
    from agent_kanban.db import AsyncSessionLocal
    from agent_kanban.mcp_server import mcp
    from agent_kanban.services import create_task
    from agent_kanban.models import TaskStatus
    from agent_kanban.schemas import TaskCreate
    async with AsyncSessionLocal() as session:
        t = await create_task(session, TaskCreate(title="t", status=TaskStatus.READY))
        task_id = t.id
        await session.close()
    await mcp.call_tool("claim_task", {"task_id": task_id, "agent": "codex"})
    result = await mcp.call_tool(
        "set_task_pr",
        {
            "task_id": task_id,
            "agent": "codex",
            "pr_url": "https://github.com/x/y/pull/1",
            "status": "open",
        },
    )
    data = _to_dict(result)
    flat = data if isinstance(data, dict) and "pr_url" in data else data.get("result", data)
    assert flat["pr_url"] == "https://github.com/x/y/pull/1"
    assert flat["pr_status"] == "open"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_mcp_server.py -v`
Expected: FAIL — `set_task_branch` and `set_task_pr` tools are not registered.

- [ ] **Step 3: Register the two tools in `mcp_server.py`**

Open `src/agent_kanban/mcp_server.py`. Add the imports for the two new service functions alongside the existing service imports:
```python
from agent_kanban.services import (
    ...
    set_task_branch as svc_set_task_branch,
    set_task_pr as svc_set_task_pr,
    ...
)
```

Then register the tools (place them near the other mutation tools, e.g. after `post_artifact`):
```python
@mcp.tool()
async def set_task_branch(task_id: int, agent: str, branch: str) -> dict:
    """Report the working branch the agent created for this task.

    Stores branch on the task so the UI can show it and request_review can
    collect a diff against the base branch. Requires task.claimed_by == agent.
    """
    async with AsyncSessionLocal() as session:
        task = await svc_set_task_branch(session, task_id, agent, branch)
        return _task_to_dict(task)


@mcp.tool()
async def set_task_pr(
    task_id: int, agent: str, pr_url: str, status: str
) -> dict:
    """Report a pull request URL and its status for this task.

    status: "open" | "merged" | "closed". Requires task.claimed_by == agent.
    """
    async with AsyncSessionLocal() as session:
        task = await svc_set_task_pr(session, task_id, agent, pr_url, status)
        return _task_to_dict(task)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_mcp_server.py -v`
Expected: PASS (all prior + 3 new). If `_to_dict`'s shape doesn't match the SDK wrapping for your pinned version, adjust `_to_dict` exactly as you did in Phase 1 Task 10 — the assertion is on the `branch`/`pr_url` fields, however they're nested.

- [ ] **Step 5: Verify the live MCP endpoint exposes both tools**

Run the server and list tools:
```bash
uv run kanban serve --port 7331 &
sleep 2
# Initialize first to get a session id, then tools/list — same pattern as Phase 1 Task 10 Step 6.
kill %1
```
Confirm `set_task_branch` and `set_task_pr` appear in the tools/list response. (Total tools: 9 prior + 2 = 11.)

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -v`
Expected: 58 prior + 3 new = 61 passing.

- [ ] **Step 7: Commit**

```bash
git add src/agent_kanban/mcp_server.py tests/test_mcp_server.py
git commit -m "feat(mcp): set_task_branch and set_task_pr tools"
```

---

## Task 4: UI badges for branch/PR + New Task modal fields

Render `branch` and PR status in `TaskCard` and `CardDetail`. Add optional `repo_path` and `base_branch` inputs to the New Task modal so the user can configure a coding task.

**Files:**
- Modify: `web/src/components/TaskCard.tsx`
- Modify: `web/src/pages/CardDetail.tsx`
- Modify: `web/src/components/NewTaskModal.tsx`
- Verify: `web/src/types.ts` (the `Task` type already has `branch`, `pr_url`, `pr_status`, `repo_path`, `base_branch` from Phase 1 — confirm and add any missing fields)

**Interfaces:**
- Consumes: existing `Task` type fields (`branch`, `pr_url`, `pr_status`, `repo_path`, `base_branch`)
- Produces: visible branch/PR badges in the card and detail header; New Task modal accepts repo_path + base_branch and posts them in the create payload.

- [ ] **Step 1: Verify `web/src/types.ts` has the Phase 3 fields**

Open `web/src/types.ts`. The `Task` interface must include `branch`, `pr_url`, `pr_status`, `repo_path`, `base_branch` — all `string | null`. If any are missing, add them. They've been on the backend `Task` since Phase 1, so they should already be present; this is a verification step.

- [ ] **Step 2: Add branch/PR badges to `TaskCard.tsx`**

Open `web/src/components/TaskCard.tsx`. After the existing `claimed_by` block (inside the card `<div>`), add:
```tsx
      {task.branch && (
        <div style={{ marginTop: 4, fontSize: 11, color: "#6366f1" }}>
          ⎇ {task.branch}
        </div>
      )}
      {task.pr_url && (
        <div style={{ marginTop: 4, fontSize: 11 }}>
          <span
            style={{
              padding: "1px 6px",
              borderRadius: 4,
              background:
                task.pr_status === "merged" ? "#dcfce7"
                : task.pr_status === "closed" ? "#fee2e2"
                : "#dbeafe",
              color:
                task.pr_status === "merged" ? "#166534"
                : task.pr_status === "closed" ? "#991b1b"
                : "#1e40af",
            }}
          >
            #{task.pr_url.split("/").pop()} · {task.pr_status ?? "open"}
          </span>
        </div>
      )}
```

- [ ] **Step 3: Add branch/PR line to `CardDetail.tsx` header**

Open `web/src/pages/CardDetail.tsx`. Find the status/claimed-by line in the header (`{task.claimed_by && ...}`). After it, add branch and PR links:
```tsx
        {task.branch && <> · ⎇ <code>{task.branch}</code></>}
        {task.pr_url && (
          <>
            {" · "}PR{" "}
            <a href={task.pr_url} target="_blank" rel="noreferrer">
              #{task.pr_url.split("/").pop()}
            </a>{" "}
            <em style={{ color: task.pr_status === "merged" ? "#166534" : "#666" }}>
              ({task.pr_status ?? "open"})
            </em>
          </>
        )}
```

- [ ] **Step 4: Add repo_path + base_branch inputs to `NewTaskModal.tsx`**

Open `web/src/components/NewTaskModal.tsx`. Add two state hooks near the existing ones:
```typescript
  const [repoPath, setRepoPath] = useState("");
  const [baseBranch, setBaseBranch] = useState("");
```

In the `submit` function, include the new fields in the create call (only send them if non-empty):
```typescript
  async function submit() {
    const t = await api.createTask({
      title,
      description,
      tags: tags.split(",").map((s) => s.trim()).filter(Boolean),
      ...(repoPath ? { repo_path: repoPath } : {}),
      ...(baseBranch ? { base_branch: baseBranch } : {}),
    });
    onCreated(t);
    onClose();
  }
```

In the JSX (after the tags input, before the action buttons), add:
```tsx
        <input
          placeholder="Repo path (optional, for coding tasks)"
          value={repoPath}
          onChange={(e) => setRepoPath(e.target.value)}
          style={{ width: "100%", marginBottom: 8 }}
        />
        <input
          placeholder="Base branch (optional, e.g. main)"
          value={baseBranch}
          onChange={(e) => setBaseBranch(e.target.value)}
          style={{ width: "100%", marginBottom: 12 }}
        />
```

- [ ] **Step 5: Verify the build**

Run: `cd web && pnpm build`
Expected: succeeds with no TypeScript errors. If `api.createTask`'s type doesn't accept `repo_path`/`base_branch`, update the `createTask` parameter type in `web/src/api.ts` to include them as optional fields.

- [ ] **Step 6: Update `api.ts` createTask type if needed**

In `web/src/api.ts`, the `createTask` method's parameter type may need to include the new optional fields:
```typescript
  async createTask(data: {
    title: string;
    description?: string;
    tags?: string[];
    status?: TaskStatus;
    repo_path?: string;
    base_branch?: string;
  }): Promise<Task> {
```

- [ ] **Step 7: Manual smoke**

With backend running, create a task via the modal with `repo_path=/some/path` and `base_branch=main`. Verify via the API that the task has those fields set. (Full diff auto-collection requires a real git repo at that path; manual verification of the diff pipeline is optional — the unit tests cover it.)

- [ ] **Step 8: Commit**

```bash
cd /Users/graywrk/src/graywrk_agents_canban
git add web/src/components/TaskCard.tsx web/src/pages/CardDetail.tsx web/src/components/NewTaskModal.tsx web/src/api.ts
git commit -m "feat(web): branch/PR badges and coding-task fields in new task modal"
```

---

## Task 5: README + Phase 3 acceptance verification

Document the git/PR workflow in the README and verify all Phase 3 acceptance criteria.

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a "Coding tasks (git/PR)" section to README**

Open `README.md`. After the existing "Agent workflow" section (added in Phase 1 Task 17), insert:
```markdown
## Coding tasks (git/PR)

For tasks that touch a git repo, set `repo_path` and `base_branch` when creating the task. The board does NOT create branches or PRs — your agent does that with its own git tools. The board records what the agent reports and renders a review diff.

Agent workflow for a coding task:
1. `claim_task` — receives `repo_path` and (if set) `base_branch`.
2. Create a branch in `repo_path` with the agent's git tool.
3. `set_task_branch(task_id, agent, branch)` — record it so the UI shows it and the diff can be collected.
4. Commit work on that branch.
5. `request_review(task_id, agent, summary)` — the board runs `git -C <repo_path> diff <base>...<branch>` once and stores the result as a diff event visible in the card's progress feed.
6. Open a PR with the agent's GitHub tool, then `set_task_pr(task_id, agent, pr_url, "open")`.
7. When merged, `set_task_pr(task_id, agent, pr_url, "merged")` then `complete_task`.

If `repo_path`, `base_branch` (or the project's `default_branch`), or `branch` is missing, diff collection is skipped silently. If `git diff` fails, an error event is recorded instead, but the review request itself still succeeds.
```

- [ ] **Step 2: Verify all acceptance criteria**

Run the full suite: `uv run pytest -v` → expect 61 passing.
Build the frontend: `cd web && pnpm build` → expect clean.
Curl the MCP tools list against a running server and confirm 11 tools including `set_task_branch` and `set_task_pr`.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document coding-task git/PR workflow (Phase 3)"
```

---

## Phase 3 Acceptance Criteria

Phase 3 is complete when all of the following hold:

- [ ] `uv run pytest -v` passes (61+ tests).
- [ ] `cd web && pnpm build` succeeds.
- [ ] The 2 new MCP tools (`set_task_branch`, `set_task_pr`) are reachable at `/mcp` and via the stdio bridge; both enforce `claimed_by == agent`.
- [ ] `request_review` on a task with `repo_path` + `branch` + a resolvable base collects a diff and stores it as a `progress_event(kind=diff)`.
- [ ] If `git diff` fails, an error progress event is recorded instead, and the task still transitions to `review`.
- [ ] The UI shows a branch badge and a colored PR badge (open/merged/closed) on cards and in the card detail header.
- [ ] The New Task modal accepts optional `repo_path` and `base_branch` inputs and includes them in the create payload.
- [ ] `git.collect_diff` is bounded by a 10s timeout; a hung git process does not stall the request.
- [ ] No DB migrations were added.

---

## Notes for the implementer

- **No DB migrations.** All Phase 3 columns already exist. If a task seems to need a migration, escalate rather than adding one.
- **Git is best-effort.** `request_review` must never fail because of git. The `_maybe_collect_review_diff` helper swallows all exceptions and records an error event instead.
- **`asyncio.create_subprocess_exec`** is used (not `subprocess.run`) so the git call doesn't block the event loop. `asyncio.wait_for` enforces the timeout.
- **The diff is refreshed every time the task re-enters `review`** — there is no "already collected" flag. This matches spec §6.2 and handles re-review after the agent pushes more commits.
- **The two new MCP tools bring the total to 11.** Phase 1 had 9; Phase 3 adds 2. The stdio bridge needs no changes (it proxies all tools).
- **`_extract_diff_filenames`** uses a regex on `+++ b/<path>` lines. This is best-effort; malformed diffs may produce an empty list, which is fine.
- **PR status colors** in the badge: open=blue, merged=green, closed=red. The status string comes straight from the agent's `set_task_pr` call — the board does not validate it against an enum (intentional, per spec §5.2 which types it as a plain string).
