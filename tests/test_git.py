"""Tests for git.collect_diff against a real temp git repo."""
import os
import tempfile
from pathlib import Path

import pytest

from agent_kanban.git import GitError, collect_diff


def _run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    import subprocess
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, env=env)


@pytest.fixture
def tmp_repo():
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d)
        # GIT_AUTHOR_* / GIT_COMMITTER_* are natively understood by git, so we
        # pass them through the subprocess env to avoid depending on a global
        # identity (CI has none). This replaces the brief's broken config loop.
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        _run(["git", "init", "-q", "-b", "main"], repo, env=env)
        (repo / "README.md").write_text("# hello\n")
        _run(["git", "add", "."], repo, env=env)
        _run(["git", "commit", "-q", "-m", "init"], repo, env=env)
        # Create a feature branch with a change.
        _run(["git", "checkout", "-q", "-b", "feat"], repo, env=env)
        (repo / "README.md").write_text("# hello world\n")
        _run(["git", "add", "."], repo, env=env)
        _run(["git", "commit", "-q", "-m", "expand greeting"], repo, env=env)
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
