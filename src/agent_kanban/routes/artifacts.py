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
