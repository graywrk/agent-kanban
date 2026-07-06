import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agent_kanban.models import TaskStatus
from agent_kanban.schemas import ArtifactCreate, ProgressCreate, TaskCreate
from agent_kanban.services import (
    claim_task,
    complete_task,
    create_task,
    get_next_task,
    post_artifact,
    post_progress,
    request_review,
)
from agent_kanban.models import ProgressKind


@pytest.mark.asyncio
async def test_create_task_defaults_to_todo(session: AsyncSession):
    t = await create_task(session, TaskCreate(title="hi"))
    assert t.status == TaskStatus.TODO
    assert t.tags == []


@pytest.mark.asyncio
async def test_get_next_task_returns_only_ready(session: AsyncSession):
    await create_task(session, TaskCreate(title="a", status=TaskStatus.TODO))
    b = await create_task(session, TaskCreate(title="b", status=TaskStatus.READY))
    nxt = await get_next_task(session, None, None, None)
    assert nxt is not None
    assert nxt.id == b.id


@pytest.mark.asyncio
async def test_get_next_task_filters_by_tag(session: AsyncSession):
    await create_task(session, TaskCreate(title="x", status=TaskStatus.READY, tags=["ui"]))
    await create_task(session, TaskCreate(title="y", status=TaskStatus.READY, tags=["backend"]))
    nxt = await get_next_task(session, tags_any=["backend"], tags_all=None, exclude_tags=None)
    assert nxt is not None
    assert nxt.tags == ["backend"]


@pytest.mark.asyncio
async def test_claim_task_atomic_and_authorizes(session: AsyncSession):
    t = await create_task(session, TaskCreate(title="t", status=TaskStatus.READY))
    r1 = await claim_task(session, t.id, "codex")
    assert r1.ok is True
    assert r1.task.claimed_by == "codex"
    assert r1.task.status == TaskStatus.IN_PROGRESS

    # Second claim attempt fails.
    r2 = await claim_task(session, t.id, "hermes")
    assert r2.ok is False
    assert "already" in (r2.reason or "").lower() or "not ready" in (r2.reason or "").lower()


@pytest.mark.asyncio
async def test_post_progress_requires_claimer(session: AsyncSession):
    t = await create_task(session, TaskCreate(title="t", status=TaskStatus.READY))
    await claim_task(session, t.id, "codex")

    # Wrong agent rejected.
    with pytest.raises(PermissionError):
        await post_progress(
            session,
            t.id,
            ProgressCreate(agent="hermes", kind=ProgressKind.TEXT, content="hi"),
        )

    # Right agent succeeds.
    ev = await post_progress(
        session,
        t.id,
        ProgressCreate(agent="codex", kind=ProgressKind.TEXT, content="hi"),
    )
    assert ev.payload["content"] == "hi"


@pytest.mark.asyncio
async def test_complete_task_sets_done(session: AsyncSession):
    t = await create_task(session, TaskCreate(title="t", status=TaskStatus.READY))
    await claim_task(session, t.id, "codex")
    done = await complete_task(session, t.id, "codex", summary="all done")
    assert done.status == TaskStatus.DONE


@pytest.mark.asyncio
async def test_complete_task_rejects_non_claimer(session: AsyncSession):
    t = await create_task(session, TaskCreate(title="t", status=TaskStatus.READY))
    await claim_task(session, t.id, "codex")
    with pytest.raises(PermissionError):
        await complete_task(session, t.id, "hermes")


@pytest.mark.asyncio
async def test_request_review_sets_review(session: AsyncSession):
    t = await create_task(session, TaskCreate(title="t", status=TaskStatus.READY))
    await claim_task(session, t.id, "codex")
    out = await request_review(session, t.id, "codex", summary="please check")
    assert out.status == TaskStatus.REVIEW


@pytest.mark.asyncio
async def test_post_artifact_rejects_path_outside_sandbox(session: AsyncSession):
    t = await create_task(session, TaskCreate(title="t", status=TaskStatus.READY))
    await claim_task(session, t.id, "codex")
    with pytest.raises(ValueError):
        await post_artifact(
            session,
            t.id,
            ArtifactCreate(agent="codex", kind="log", path="/etc/passwd"),
        )


@pytest.mark.asyncio
async def test_post_progress_blocked_publishes_to_board(session: AsyncSession):
    """BLOCKED transition must fan out to the board channel, not just task:{id}."""
    from agent_kanban.events import event_bus
    import asyncio
    received = []
    async def consumer():
        async for evt in event_bus.subscribe("board"):
            received.append(evt)
            break
    task = await create_task(session, TaskCreate(title="t", status=TaskStatus.READY))
    await claim_task(session, task.id, "codex")
    consumer_task = asyncio.create_task(consumer())
    await asyncio.sleep(0.05)
    await post_progress(
        session,
        task.id,
        ProgressCreate(
            agent="codex",
            kind=ProgressKind.STATUS_CHANGE,
            content="stuck on env",
            status={"from": "in_progress", "to": "blocked", "note": "need user input"},
        ),
    )
    await asyncio.wait_for(consumer_task, timeout=1.0)
    assert any(evt.get("type") == "task_blocked" for evt in received)


@pytest.mark.asyncio
async def test_list_comments_marks_only_other_authors_seen(session: AsyncSession):
    """get_comments must not mark the calling agent's own comments as seen."""
    from agent_kanban.services import post_comment, list_comments
    t = await create_task(session, TaskCreate(title="t", status=TaskStatus.TODO))
    # codex writes a comment; user writes a comment
    await post_comment(session, t.id, "codex", "i am working")
    await post_comment(session, t.id, "user", "good luck")
    # codex reads comments
    comments = await list_comments(session, t.id, since_id=None, mark_seen_by="codex")
    # codex's own comment must remain seen_by_agent=False (it's not a message TO codex)
    codex_own = [c for c in comments if c.author == "codex"][0]
    user_to_codex = [c for c in comments if c.author == "user"][0]
    assert codex_own.seen_by_agent is False
    assert user_to_codex.seen_by_agent is True


# ---- Phase 3: set_task_branch / set_task_pr / review diff auto-collection ----
from unittest.mock import AsyncMock, patch  # noqa: E402

from agent_kanban.git import GitError  # noqa: E402
from agent_kanban.services import (  # noqa: E402
    get_task,
    set_task_branch,
    set_task_pr,
)


@pytest.mark.asyncio
async def test_set_task_branch_requires_claimer(session: AsyncSession):
    t = await create_task(session, TaskCreate(title="t", status=TaskStatus.READY))
    await claim_task(session, t.id, "codex")
    with pytest.raises(PermissionError):
        await set_task_branch(session, t.id, "hermes", "feat/x")


@pytest.mark.asyncio
async def test_set_task_branch_sets_branch(session: AsyncSession):
    t = await create_task(session, TaskCreate(title="t", status=TaskStatus.READY))
    await claim_task(session, t.id, "codex")
    out = await set_task_branch(session, t.id, "codex", "feat/dark-mode")
    assert out.branch == "feat/dark-mode"


@pytest.mark.asyncio
async def test_set_task_pr_requires_claimer(session: AsyncSession):
    t = await create_task(session, TaskCreate(title="t", status=TaskStatus.READY))
    await claim_task(session, t.id, "codex")
    with pytest.raises(PermissionError):
        await set_task_pr(session, t.id, "hermes", "https://github.com/x/y/pull/1", "open")


@pytest.mark.asyncio
async def test_set_task_pr_sets_url_and_status(session: AsyncSession):
    t = await create_task(session, TaskCreate(title="t", status=TaskStatus.READY))
    await claim_task(session, t.id, "codex")
    out = await set_task_pr(
        session, t.id, "codex", "https://github.com/x/y/pull/1", "open"
    )
    assert out.pr_url == "https://github.com/x/y/pull/1"
    assert out.pr_status == "open"


@pytest.mark.asyncio
async def test_request_review_collects_diff_when_configured(session: AsyncSession):
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
    fake_stats = [{"path": "f.txt", "added": 1, "deleted": 1}]
    with patch("agent_kanban.services.collect_diff", new=AsyncMock(return_value=fake_diff)), \
         patch("agent_kanban.services.collect_diffstats", new=AsyncMock(return_value=fake_stats)):
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
    assert diff_events[0].payload["files"] == ["f.txt"]
    assert diff_events[0].payload["stats"]["f.txt"] == "+1 -1"


@pytest.mark.asyncio
async def test_request_review_skips_diff_without_repo_path(session: AsyncSession):
    t = await create_task(session, TaskCreate(title="t", status=TaskStatus.READY))
    await claim_task(session, t.id, "codex")

    with patch("agent_kanban.services.collect_diff", new=AsyncMock()) as mock_diff:
        await request_review(session, t.id, "codex", summary="review please")
        mock_diff.assert_not_called()


@pytest.mark.asyncio
async def test_request_review_records_error_event_on_git_failure(session: AsyncSession):
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
    refreshed = await get_task(session, t.id)
    assert refreshed.status == TaskStatus.REVIEW


@pytest.mark.asyncio
async def test_request_review_diff_survives_numstat_failure(session: AsyncSession):
    """If collect_diffstats fails after collect_diff succeeds, the diff is still
    stored with empty stats — not lost entirely."""
    from sqlmodel import select
    from agent_kanban.models import ProgressEvent

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
    with patch("agent_kanban.services.collect_diff", new=AsyncMock(return_value=fake_diff)), \
         patch("agent_kanban.services.collect_diffstats", new=AsyncMock(side_effect=GitError("numstat boom"))):
        await request_review(session, t.id, "codex", summary="review please")

    stmt = select(ProgressEvent).where(ProgressEvent.task_id == t.id)
    result = await session.execute(stmt)
    events = list(result.scalars())
    diff_events = [e for e in events if e.kind.value == "diff"]
    error_events = [e for e in events if e.kind.value == "error"]
    # Diff survived.
    assert len(diff_events) == 1
    assert "old" in diff_events[0].payload["content"]
    # Stats degraded to empty.
    assert diff_events[0].payload["stats"] == {}
    assert diff_events[0].payload["files"] == []
    # No error event was written for the numstat failure.
    assert error_events == []
    # Status moved to review.
    refreshed = await get_task(session, t.id)
    assert refreshed.status == TaskStatus.REVIEW


@pytest.mark.asyncio
async def test_post_progress_artifact_ref_injects_id(session: AsyncSession):
    """When an artifact_ref event references a registered artifact path, the
    stored payload's artifact dict includes the artifact's id so the UI can
    fetch via /api/artifacts/{id}/content."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        repo = Path(d)
        (repo / "out.txt").write_text("hi")
        t = await create_task(
            session,
            TaskCreate(title="t", status=TaskStatus.READY, repo_path=str(repo)),
        )
        await claim_task(session, t.id, "codex")
        # Register the artifact (post_artifact enforces the sandbox).
        art = await post_artifact(
            session,
            t.id,
            ArtifactCreate(agent="codex", kind="log", path=str(repo / "out.txt")),
        )
        # Now post an artifact_ref progress event referencing the same path.
        ev = await post_progress(
            session,
            t.id,
            ProgressCreate(
                agent="codex",
                kind=ProgressKind.ARTIFACT_REF,
                content="see attached log",
                artifact={"path": str(repo / "out.txt"), "kind": "log"},
            ),
        )
        assert ev.payload["artifact"]["id"] == art.id
        assert ev.payload["artifact"]["path"] == str(repo / "out.txt")


@pytest.mark.asyncio
async def test_post_progress_artifact_ref_without_matching_row(session: AsyncSession):
    """If no Artifact row matches the path, the payload is stored without id;
    the UI falls back gracefully."""
    t = await create_task(session, TaskCreate(title="t", status=TaskStatus.READY))
    await claim_task(session, t.id, "codex")
    ev = await post_progress(
        session,
        t.id,
        ProgressCreate(
            agent="codex",
            kind=ProgressKind.ARTIFACT_REF,
            content="orphan reference",
            artifact={"path": "/nonexistent/file", "kind": "file"},
        ),
    )
    assert "id" not in ev.payload["artifact"]
    assert ev.payload["artifact"]["path"] == "/nonexistent/file"
