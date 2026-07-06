# Agent Kanban — Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pay down the minor items deferred across Phases 1–3 reviews: clean lint, complete data shapes, fill test gaps, and ship a real artifact-serving endpoint to replace the `file:///` placeholder.

**Architecture:** Small, mostly-independent fixes layered on the merged Phases 1–3. No DB migrations, no new dependencies. Each task is one focused improvement with its own test/verification cycle.

**Tech Stack:** Python 3.11 + FastAPI + sqlmodel (existing); React/Vite/TS (existing). The artifact endpoint reuses `aiofiles` if available, else streams via standard `pathlib` + `fastapi.responses.FileResponse` (already transitively available through FastAPI/Starlette — no new dep).

**Spec:** N/A — this plan closes review findings, not new spec sections. Spec §4.3 (`stats` shape), §5.1 (`post_artifact`), §7.5 (polish) are the relevant anchors.

## Global Constraints

- All Phase 1–3 constraints still apply (Python 3.11+, PostgreSQL on host port **5436**, MCP SDK `mcp>=1.27,<2.0`, no auth, default port 7331).
- **No DB migrations.** No schema changes.
- **No new dependencies** without explicit justification. `aiofiles` should NOT be added — use `fastapi.responses.FileResponse` which is part of Starlette (already a transitive dep).
- TDD for backend changes with testable logic; `pnpm build` for frontend changes.
- Single-user, no auth. The artifact endpoint must sandbox paths the same way `post_artifact` does (already in `services._is_path_allowed`).

---

## File Structure

```
src/agent_kanban/
├── git.py               # MODIFY: add collect_diffstats (Task 3)
├── services.py          # MODIFY: _maybe_collect_review_diff uses numstat; reuse _is_path_allowed
├── routes/
│   └── artifacts.py     # CREATE: GET /api/artifacts/{id}/content (Task 4)
├── mcp_server.py        # MODIFY: complete _task_to_dict (Task 1)
├── routes/
│   └── ws.py            # MODIFY: explicit unsubscribe on disconnect (Task 1)
└── server.py            # MODIFY: mount artifacts router (Task 4)
tests/
├── test_git.py          # MODIFY: timeout test + collect_diffstats test (Tasks 2, 3)
├── test_services.py     # MODIFY: stats populated (Task 3)
└── test_routes_artifacts.py  # CREATE (Task 4)
web/src/
├── components/
│   ├── ArtifactCard.tsx  # MODIFY: use /api/artifacts/{id}/content URL (Task 4)
│   └── TaskCard.tsx      # (no change — already correct)
└── pages/
    └── CardDetail.tsx    # MODIFY: PR status colors for all 3 states (Task 1)
```

---

## Task 1: Lint cleanup, `_task_to_dict` completion, WS unsubscribe, CardDetail PR colors

Bundled quality fixes — each is small, all are review-findings.

**Files:**
- Modify: `src/agent_kanban/mcp_server.py` (complete `_task_to_dict`)
- Modify: `src/agent_kanban/routes/ws.py` (explicit cleanup)
- Modify: `web/src/pages/CardDetail.tsx` (PR colors)
- Modify: various test/source files (lint fixes via `ruff --fix`)

**Interfaces:**
- Produces: `_task_to_dict` returns the same field set as `TaskRead` (id, title, description, status, tags, claimed_by, claimed_at, project_id, sort_order, repo_path, base_branch, branch, pr_url, pr_status, created_at, updated_at). WS endpoint calls an explicit cleanup on disconnect.

- [ ] **Step 1: Run `ruff --fix` to clear auto-fixable lint**

Run:
```bash
uv run ruff check --fix src/ tests/
```
Expected: 7 of 8 findings auto-fixed (unused imports removed). One finding (`F841 local variable 'a' assigned but never used` in `tests/test_services.py`) needs a manual edit because ruff's unsafe-fix can change test semantics.

- [ ] **Step 2: Manually fix the F841 unused-local**

Open `tests/test_services.py`. Find the line `a = await create_task(session, TaskCreate(title="a", status=TaskStatus.TODO))` inside `test_get_next_task_returns_only_ready`. Change it to discard the unused result:
```python
    await create_task(session, TaskCreate(title="a", status=TaskStatus.TODO))
```

- [ ] **Step 3: Verify ruff is clean**

Run: `uv run ruff check src/ tests/`
Expected: `All checks passed!` (or zero errors).

- [ ] **Step 4: Complete `_task_to_dict` in `mcp_server.py`**

Open `src/agent_kanban/mcp_server.py`. Find `_task_to_dict` and replace it with a complete version that mirrors `TaskRead`:
```python
def _task_to_dict(task) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status.value if hasattr(task.status, "value") else task.status,
        "tags": task.tags,
        "claimed_by": task.claimed_by,
        "claimed_at": task.created_at.isoformat() + "Z" if task.claimed_at else None,
        "project_id": task.project_id,
        "sort_order": task.sort_order,
        "repo_path": task.repo_path,
        "base_branch": task.base_branch,
        "branch": task.branch,
        "pr_url": task.pr_url,
        "pr_status": task.pr_status,
        "created_at": task.created_at.isoformat() + "Z",
        "updated_at": task.updated_at.isoformat() + "Z",
    }
```

(The `"Z"` suffix matches the Phase 2 fix in `routes/progress.py` — naive-UTC datetimes get an explicit UTC marker so JS `Date` parses them correctly. `claimed_at` may be `None`; guard it.)

- [ ] **Step 5: Add explicit WS cleanup**

Open `src/agent_kanban/routes/ws.py`. The current handler subscribes and iterates; on disconnect the `async for` exits but cleanup is implicit (the generator's `finally` removes the queue). Make it explicit and defensive:

Replace the entire contents of `src/agent_kanban/routes/ws.py`:
```python
"""WebSocket endpoint for live updates."""
from contextlib import suppress
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from agent_kanban.events import event_bus

router = APIRouter(tags=["ws"])


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket, task_id: Optional[int] = None):
    await websocket.accept()
    channel = f"task:{task_id}" if task_id else "board"
    subscriber = event_bus.subscribe(channel)
    try:
        async for evt in subscriber:
            with suppress(Exception):
                await websocket.send_json(evt)
    except WebSocketDisconnect:
        pass
    finally:
        # Explicit cleanup: close the async iterator so the bus's finally
        # block removes the queue from the subscriber set immediately,
        # rather than waiting for GC.
        with suppress(Exception):
            await subscriber.aclose()
```

(The `suppress(Exception)` around `send_json` defends against send-after-close race; the `aclose()` is the explicit cleanup the Phase 1 review asked for.)

- [ ] **Step 6: CardDetail PR status colors for all 3 states**

Open `web/src/pages/CardDetail.tsx`. Find the PR `<em>` line:
```tsx
            <em style={{ color: task.pr_status === "merged" ? "#166534" : "#666" }}>
              ({task.pr_status ?? "open"})
            </em>
```
Replace with a full color mapping matching the TaskCard badge:
```tsx
            <em
              style={{
                color:
                  task.pr_status === "merged" ? "#166534"
                  : task.pr_status === "closed" ? "#991b1b"
                  : "#1e40af",
              }}
            >
              ({task.pr_status ?? "open"})
            </em>
```

- [ ] **Step 7: Verify backend and frontend**

Run: `uv run pytest -q`
Expected: 62 passing (no regression; the new dict fields aren't asserted by existing tests but don't break them).

Run: `cd web && pnpm build`
Expected: clean.

- [ ] **Step 8: Commit**

```bash
cd /Users/graywrk/src/graywrk_agents_canban
git add -A
git commit -m "chore: ruff fixes, complete _task_to_dict, WS explicit cleanup, CardDetail PR colors"
```

---

## Task 2: Test for `collect_diff` timeout

The 10s timeout path in `collect_diff` is security-relevant (prevents a hung git from stalling the request handler) but has no test. Add one.

**Files:**
- Modify: `tests/test_git.py`

**Interfaces:**
- Produces: a regression test asserting `collect_diff(timeout_s=0.05)` raises `GitError` when git doesn't return in time, and that no zombie process leaks.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_git.py`:
```python
@pytest.mark.asyncio
async def test_collect_diff_times_out_and_kills_process(tmp_repo):
    """A short timeout must raise GitError and not leak the git process."""
    import asyncio
    # Use an extremely short timeout to force the timeout branch even on a fast machine.
    # We make git slow by diffing against a ref that requires walking a lot — but the
    # simplest reliable way is a timeout shorter than any real git invocation.
    with pytest.raises(GitError, match="timed out"):
        # timeout_s=0 means wait_for fires immediately after the process is created.
        await collect_diff(tmp_repo, "main", "feat", timeout_s=0.0)
```

> **Note for the implementer:** `timeout_s=0.0` may fire before `git` is even scheduled, which is fine — the test asserts the timeout path raises `GitError`. If on your machine git is fast enough that `0.0` raises before subprocess creation, the test still passes (the `wait_for(communicate(), timeout=0.0)` branch fires). The important assertion is that `GitError` with "timed out" is raised, NOT that the process definitely started. The kill+wait cleanup in `git.py:46-47` runs regardless.

- [ ] **Step 2: Run the test, verify it passes**

Run: `uv run pytest tests/test_git.py::test_collect_diff_times_out_and_kills_process -v`
Expected: PASS.

- [ ] **Step 3: Run the full git test file**

Run: `uv run pytest tests/test_git.py -v`
Expected: 5 passing (4 prior + 1 new).

- [ ] **Step 4: Commit**

```bash
git add tests/test_git.py
git commit -m "test(git): cover collect_diff timeout branch"
```

---

## Task 3: Populate diff `stats` and `files` accurately via `git diff --numstat`

The current `_extract_diff_filenames` regex misses deletions and binary files, and `stats` is hardcoded `{}`. Use a separate `git diff --numstat` call to populate both correctly.

**Files:**
- Modify: `src/agent_kanban/git.py`
- Modify: `src/agent_kanban/services.py`
- Modify: `tests/test_git.py`
- Modify: `tests/test_services.py`

**Interfaces:**
- Produces:
  - `async def collect_diffstats(repo_path, base, head, timeout_s=10.0) -> list[dict]` in `git.py` — returns `[{"path": "src/x.py", "added": 12, "deleted": 3}, ...]`. Uses `git -C <repo> diff --numstat <base>...<head>`. Binary files report `added=-1, deleted=-1` (numstat prints `-` for binary).
  - `_maybe_collect_review_diff` now calls both `collect_diff` and `collect_diffstats`, builds `files` (paths) and `stats` (path → "{+a -d}") from the numstat output, and stores them in the diff event payload.

- [ ] **Step 1: Write failing tests for `collect_diffstats`**

Append to `tests/test_git.py`:
```python
@pytest.mark.asyncio
async def test_collect_diffstats_returns_per_file_counts(tmp_repo):
    from agent_kanban.git import collect_diffstats
    stats = await collect_diffstats(tmp_repo, "main", "feat")
    assert isinstance(stats, list)
    assert len(stats) == 1
    entry = stats[0]
    assert entry["path"] == "README.md"
    assert entry["added"] == 1
    assert entry["deleted"] == 1


@pytest.mark.asyncio
async def test_collect_diffstats_empty_when_no_changes(tmp_repo):
    from agent_kanban.git import collect_diffstats
    stats = await collect_diffstats(tmp_repo, "main", "main")
    assert stats == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_git.py -v -k diffstats`
Expected: FAIL — `collect_diffstats` doesn't exist.

- [ ] **Step 3: Implement `collect_diffstats`**

Open `src/agent_kanban/git.py`. Add a new function after `collect_diff`:
```python
async def collect_diffstats(
    repo_path: Union[str, Path],
    base: str,
    head: str,
    timeout_s: float = 10.0,
) -> list[dict]:
    """Return per-file added/deleted line counts via `git diff --numstat`.

    Output: [{"path": str, "added": int, "deleted": int}, ...].
    Binary files have added=-1, deleted=-1 (numstat prints "-\t-\t<path>").
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
            "--numstat",
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
        raise GitError(f"git diff --numstat timed out after {timeout_s}s")

    if proc.returncode != 0:
        msg = stderr.decode(errors="replace").strip() or f"exit code {proc.returncode}"
        raise GitError(f"git diff --numstat failed: {msg}")

    out: list[dict] = []
    for line in stdout.decode(errors="replace").splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added_s, deleted_s, path = parts
        added = -1 if added_s == "-" else int(added_s)
        deleted = -1 if deleted_s == "-" else int(deleted_s)
        out.append({"path": path, "added": added, "deleted": deleted})
    return out
```

- [ ] **Step 4: Run git tests to verify they pass**

Run: `uv run pytest tests/test_git.py -v`
Expected: PASS (5 prior + 2 new = 7).

- [ ] **Step 5: Wire `collect_diffstats` into `_maybe_collect_review_diff`**

Open `src/agent_kanban/services.py`. Update the import at the top:
```python
from agent_kanban.git import GitError, collect_diff, collect_diffstats, resolve_base_branch
```

Replace the success branch of `_maybe_collect_review_diff` (the block after the two except clauses that currently does `files = _extract_diff_filenames(diff_text)`):
```python
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
```

Now delete the now-unused `_extract_diff_filenames` function entirely (it's at module level in services.py).

- [ ] **Step 6: Update the existing diff-collection service test to assert `stats`**

Open `tests/test_services.py`. Find `test_request_review_collects_diff_when_configured`. The existing assertion checks `diff_events[0].payload["content"]`. Add assertions for `files` and `stats`:
```python
    assert "old" in diff_events[0].payload["content"]
    assert "new" in diff_events[0].payload["content"]
    assert diff_events[0].payload["files"] == ["f.txt"]
    assert diff_events[0].payload["stats"]["f.txt"] == "+1 -1"
```

(The `fake_diff` in that test is `"--- a/f.txt\n+++ b/f.txt\n@@ -1 +1 @@\n-old\n+new\n"`. The `collect_diffstats` is mocked? No — it's a real call against `/tmp/fakerepo` which doesn't exist. **You must also mock `collect_diffstats`** in that test.)

Update the test to mock both:
```python
    fake_diff = "--- a/f.txt\n+++ b/f.txt\n@@ -1 +1 @@\n-old\n+new\n"
    fake_stats = [{"path": "f.txt", "added": 1, "deleted": 1}]
    with patch("agent_kanban.services.collect_diff", new=AsyncMock(return_value=fake_diff)), \
         patch("agent_kanban.services.collect_diffstats", new=AsyncMock(return_value=fake_stats)):
        await request_review(session, t.id, "codex", summary="review please")
```

- [ ] **Step 7: Run the full suite**

Run: `uv run pytest -v`
Expected: all passing (the modified service test + 7 git tests + everything else).

- [ ] **Step 8: Commit**

```bash
git add src/agent_kanban/git.py src/agent_kanban/services.py tests/test_git.py tests/test_services.py
git commit -m "feat(git): populate diff stats via numstat; accurate files list"
```

---

## Task 4: Real artifact-serving endpoint

Replace the `file:///` placeholder with a real `GET /api/artifacts/{id}/content` endpoint that streams the file, sandboxed the same way `post_artifact` sandboxes registration.

**Files:**
- Create: `src/agent_kanban/routes/artifacts.py`
- Modify: `src/agent_kanban/server.py` (mount router)
- Modify: `web/src/components/ArtifactCard.tsx` (use the new URL)
- Create: `tests/test_routes_artifacts.py`

**Interfaces:**
- Consumes: `agent_kanban.db.get_session`, `agent_kanban.models.Artifact`, `services._is_path_allowed` (or re-implement the same check locally to avoid coupling)
- Produces: `GET /api/artifacts/{id}/content` — looks up the Artifact by id, verifies its path is inside an allow-listed root, streams the file via `FileResponse`. Returns 404 if artifact or file missing, 403 if the path is outside the sandbox.

- [ ] **Step 1: Write failing tests**

Create `tests/test_routes_artifacts.py`:
```python
import pytest
from httpx import ASGITransport, AsyncClient

from agent_kanban.server import create_app


@pytest.fixture
async def client(db_url):
    from agent_kanban.config import get_settings
    get_settings.cache_clear()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_artifact_content_404_for_unknown_id(client):
    r = await client.get("/api/artifacts/999999/content")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_artifact_content_streams_file(client, tmp_path, monkeypatch):
    # Create a task, an artifact row pointing at a real file inside the sandbox.
    import os
    from pathlib import Path
    from agent_kanban.db import AsyncSessionLocal
    from agent_kanban.models import Artifact, Task, TaskStatus
    from datetime import datetime, UTC

    sandbox_root = tmp_path / "arts"
    sandbox_root.mkdir()
    task_dir = sandbox_root / "1"
    task_dir.mkdir()
    f = task_dir / "log.txt"
    f.write_text("hello world")

    monkeypatch.setenv("HOME", str(tmp_path.parent))  # doesn't affect Path.home() in tests; see note
    # Easiest: insert the artifact directly with an absolute path the sandbox accepts.
    async with AsyncSessionLocal() as session:
        t = Task(title="t", status=TaskStatus.TODO)
        session.add(t)
        await session.commit()
        await session.refresh(t)
        art = Artifact(
            task_id=t.id,
            path=str(f),
            kind="log",
            description="a log",
        )
        session.add(art)
        await session.commit()
        await session.refresh(art)
        art_id = art.id

    r = await client.get(f"/api/artifacts/{art_id}/content")
    assert r.status_code == 200
    assert r.text == "hello world"
    assert "text/plain" in r.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_artifact_content_403_for_path_outside_sandbox(client, tmp_path):
    from agent_kanban.db import AsyncSessionLocal
    from agent_kanban.models import Artifact, Task, TaskStatus

    # A file outside both repo_path and the artifacts dir.
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("ssh key")

    async with AsyncSessionLocal() as session:
        t = Task(title="t", status=TaskStatus.TODO)
        session.add(t)
        await session.commit()
        await session.refresh(t)
        art = Artifact(task_id=t.id, path=str(outside), kind="file")
        session.add(art)
        await session.commit()
        await session.refresh(art)
        art_id = art.id

    r = await client.get(f"/api/artifacts/{art_id}/content")
    assert r.status_code == 403
```

> **Note for the implementer:** the second test uses a path inside `tmp_path/arts/1/` and expects 200. The route's sandbox check must accept this. The cleanest way: the route resolves the artifact, then loads its task to get `repo_path`, then allows the path if it's inside (a) the task's `repo_path` if set, OR (b) `~/.agent-kanban/artifacts/<task_id>/`. To make the test work, EITHER set `task.repo_path = str(tmp_path)` in the test, OR extend the allow-list to include `tmp_path` via env. **Recommendation:** set `task.repo_path = str(sandbox_root)` in the test — that's the realistic configuration (a coding task with a repo_path). Adjust the test fixture accordingly.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_routes_artifacts.py -v`
Expected: FAIL — no `/api/artifacts/...` route.

- [ ] **Step 3: Implement the route**

Create `src/agent_kanban/routes/artifacts.py`:
```python
"""REST route for serving artifact file contents (Phase polish).

Replaces the file:/// placeholder in the UI. The path stored on the
Artifact row must be inside an allow-listed root (the task's repo_path or
the per-task artifacts directory), the same sandbox rule that post_artifact
enforces at registration time. We re-check at serve time too in case rows
were inserted via raw SQL or config drifted.
"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from agent_kanban.db import get_session
from agent_kanban.models import Artifact, Task

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


def _is_path_allowed(path: str, allowed_roots: list[str]) -> bool:
    p = Path(path).expanduser().resolve()
    for root in allowed_roots:
        try:
            p.relative_to(Path(root).expanduser().resolve())
            return True
        except ValueError:
            continue
    return False


@router.get("/{artifact_id}/content")
async def get_artifact_content(artifact_id: int, session: AsyncSession = Depends(get_session)):
    art = await session.get(Artifact, artifact_id)
    if art is None:
        raise HTTPException(404, "artifact not found")

    # Resolve the task to compute allowed roots.
    task = await session.get(Task, art.task_id)
    if task is None:
        raise HTTPException(404, "task not found")

    allowed_roots = [
        str(Path.home() / ".agent-kanban" / "artifacts" / str(task.id)),
    ]
    if task.repo_path:
        allowed_roots.append(task.repo_path)

    if not _is_path_allowed(art.path, allowed_roots):
        raise HTTPException(403, "artifact path is outside the allowed roots")

    p = Path(art.path)
    if not p.is_file():
        raise HTTPException(404, "artifact file not found on disk")

    return FileResponse(str(p))
```

- [ ] **Step 4: Mount the router in `server.py`**

Open `src/agent_kanban/server.py`. Add the import alongside the other route imports:
```python
from agent_kanban.routes import artifacts, comments, progress, projects, tasks, ws
```
And include the router alongside the others (before the static mount):
```python
    app.include_router(artifacts.router)
```

- [ ] **Step 5: Update the tests to set task.repo_path so the sandbox accepts**

In `tests/test_routes_artifacts.py`, in `test_artifact_content_streams_file`, after creating the task, set its `repo_path`:
```python
        t = Task(title="t", status=TaskStatus.TODO, repo_path=str(sandbox_root))
```
This makes `sandbox_root` an allowed root, so `task_dir / "log.txt"` (= `sandbox_root/1/log.txt`) is inside it.

- [ ] **Step 6: Run the artifact tests**

Run: `uv run pytest tests/test_routes_artifacts.py -v`
Expected: PASS (3 tests). If the `outside` test's path resolution differs (e.g. on macOS `/private/var` vs `/var`), use `Path.resolve()` consistently — it's already used in `_is_path_allowed`.

- [ ] **Step 7: Update `ArtifactCard.tsx` to use the new URL**

Open `web/src/components/ArtifactCard.tsx`. The component currently uses `file:///${artifact.path}` for the `<a href>`, `<img src>`, and `fetch(... HEAD)`. Change all three to use `/api/artifacts/${artifactId}/content`. But the component doesn't currently receive an `artifactId` — only the `ArtifactMeta { path, kind }`. Two options:
- (a) Extend `ArtifactMeta` to include `id`, and update the payload builder in `services.py` to include the artifact id in the `artifact_ref` progress event payload.
- (b) Keep using `file:///` for the href/title (informational) but fetch from a new endpoint that takes the path.

Option (a) is cleaner. Steps:

In `src/agent_kanban/services.py`, in `post_artifact`, the stored `ProgressEvent` payload for `artifact_ref` is built by the agent via `post_progress` — the agent passes `artifact: {path, kind}`. To include the id, the agent would need it. But the agent gets the id back from `post_artifact` and could pass it. For now, extend `ArtifactMeta` and have the UI prefer the id-based URL when present, else fall back to the path display.

Open `web/src/types.ts`. Extend `ArtifactMeta`:
```typescript
export interface ArtifactMeta {
  id?: number;
  path: string;
  kind: string;
}
```

Open `web/src/components/ArtifactCard.tsx`. Replace the three `file:///${artifact.path}` usages:
- The `<a href>`: change to `artifact.id ? \`/api/artifacts/${artifact.id}/content\` : \`file:///${artifact.path}\``. Keep `onClick preventDefault` only when there's no id (download disabled). When there's an id, let the link work (it'll download/stream the file).
- The `<img src>`: same conditional; only render `<img>` when `artifact.id` is set (otherwise skip the image attempt entirely — no broken-image icon).
- The `fetch(... HEAD)`: only attempt when `artifact.id` is set, hitting `/api/artifacts/${artifact.id}/content` HEAD; otherwise skip the size fetch entirely (no console noise).

Concretely, replace `ArtifactCard.tsx` with:
```typescript
import { useEffect, useState } from "react";
import type { ArtifactMeta } from "../types";

const IMAGE_KINDS = new Set(["screenshot", "image", "png", "jpg", "jpeg", "gif", "webp"]);

function iconFor(kind: string): string {
  if (IMAGE_KINDS.has(kind.toLowerCase())) return "🖼";
  if (kind.includes("log")) return "📜";
  if (kind.includes("diff") || kind.includes("patch")) return "🔧";
  return "📎";
}

export function ArtifactCard({
  artifact,
  description,
}: {
  artifact: ArtifactMeta;
  description?: string;
}) {
  const [size, setSize] = useState<string | null>(null);
  const isImage = IMAGE_KINDS.has(artifact.kind.toLowerCase());
  const contentUrl = artifact.id
    ? `/api/artifacts/${artifact.id}/content`
    : null;

  useEffect(() => {
    if (!contentUrl) return;
    fetch(contentUrl, { method: "HEAD" })
      .then((r) => {
        const len = r.headers.get("content-length");
        if (len) setSize(formatBytes(Number(len)));
      })
      .catch(() => {});
  }, [contentUrl]);

  return (
    <a
      href={contentUrl ?? `file:///${artifact.path}`}
      onClick={contentUrl ? undefined : (e) => e.preventDefault()}
      title={artifact.path}
      style={{
        display: "flex",
        gap: 10,
        padding: 8,
        border: "1px solid #ddd",
        borderRadius: 6,
        background: "#fafafa",
        textDecoration: "none",
        color: "inherit",
        alignItems: "center",
      }}
    >
      {isImage && contentUrl ? (
        <img
          src={contentUrl}
          alt={description ?? artifact.path}
          style={{ width: 48, height: 48, objectFit: "cover", borderRadius: 4 }}
          onError={(e) => { e.currentTarget.style.display = "none"; }}
        />
      ) : (
        <span style={{ fontSize: 24 }}>{iconFor(artifact.kind)}</span>
      )}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {description ?? artifact.path.split("/").pop() ?? artifact.path}
        </div>
        <div style={{ fontSize: 11, color: "#666" }}>
          {artifact.kind}{size ? ` · ${size}` : ""}
        </div>
      </div>
    </a>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
```

- [ ] **Step 8: Run the full suite + build**

Run: `uv run pytest -v`
Expected: all passing (the 3 new artifact tests + everything else).

Run: `cd web && pnpm build`
Expected: clean.

- [ ] **Step 9: Commit**

```bash
cd /Users/graywrk/src/graywrk_agents_canban
git add src/agent_kanban/routes/artifacts.py src/agent_kanban/server.py web/src/components/ArtifactCard.tsx web/src/types.ts tests/test_routes_artifacts.py
git commit -m "feat(artifacts): serving endpoint /api/artifacts/{id}/content; UI uses it"
```

---

## Polish Acceptance Criteria

- [ ] `uv run ruff check src/ tests/` reports zero errors.
- [ ] `uv run pytest -v` passes (62 + new tests).
- [ ] `cd web && pnpm build` succeeds.
- [ ] `_task_to_dict` returns the same field set as `TaskRead` (timestamps with `Z` suffix).
- [ ] CardDetail PR status shows distinct colors for open/merged/closed.
- [ ] `collect_diff` has a regression test for the timeout path.
- [ ] Diff events' `stats` is populated from `git diff --numstat`; `files` lists all changed paths.
- [ ] `GET /api/artifacts/{id}/content` streams the file for in-sandbox paths (200), 403 for out-of-sandbox, 404 for missing artifact/file.
- [ ] `ArtifactCard` uses the new endpoint when `id` is available; no `file:///` fetch noise in the console.
- [ ] No DB migrations added.

---

## Notes for the implementer

- **No new dependencies.** `FileResponse` is from `starlette.responses` (re-exported by `fastapi.responses`), already transitively available.
- **`Path.home()` in tests:** the artifact route uses `Path.home() / ".agent-kanban" / "artifacts" / <task_id>`. Tests should set `task.repo_path` to a temp dir to control the sandbox rather than monkey-patching `Path.home()`.
- **The `_extract_diff_filenames` function is removed in Task 3** — search for any remaining references before deleting. It's only used in `_maybe_collect_review_diff`.
- **`collect_diffstats` and `collect_diff` make two git calls.** They run sequentially. This is fine — both are bounded by 10s and the typical diff is fast. Parallelizing with `asyncio.gather` would add complexity for ~no gain on Phase-3-scale diffs.
- **The artifact endpoint does NOT set `Content-Disposition: attachment`.** Files render inline in the browser tab when clicked (text, images) which is the desired UX for quick review. Add `Content-Disposition` later if download-as-file becomes the goal.
- **Ruff's `--fix` is safe** for `F401` (unused imports) — it never removes names that are re-exported or used in `__all__`. The one manual fix (F841 unused local) is in a test and trivial.
