"""Smoke tests that models persist correctly."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel, select

from agent_kanban.models import ProgressEvent, Task, TaskStatus


@pytest.mark.asyncio
async def test_task_persists_with_defaults(db_url):
    engine = create_async_engine(db_url, echo=False)
    async with AsyncSession(engine) as session:
        task = Task(title="Implement dark mode", description="add toggle")
        session.add(task)
        await session.commit()
        await session.refresh(task)

        stmt = select(Task).where(Task.id == task.id)
        result = await session.execute(stmt)
        fetched = result.scalar_one()

    assert fetched.status == TaskStatus.TODO
    assert fetched.tags == []
    assert fetched.claimed_by is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_progress_event_with_jsonb_payload(db_url):
    engine = create_async_engine(db_url)
    async with AsyncSession(engine) as session:
        task = Task(title="t1")
        session.add(task)
        await session.commit()
        await session.refresh(task)

        ev = ProgressEvent(
            task_id=task.id,
            agent="codex",
            kind="text",
            payload={"content": "starting work"},
        )
        session.add(ev)
        await session.commit()
        await session.refresh(ev)

        assert ev.payload == {"content": "starting work"}
        assert ev.created_at is not None
    await engine.dispose()
