"""task organization: priority, preferred_model, created_by + ordering index

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-10-12 20:00:00.000000

Adds three columns to ``task``:

- ``priority``: Postgres enum ``taskpriority`` (critical/high/medium/low),
  existing rows backfilled to ``medium``. Drives get_next_task ordering.
- ``preferred_model``: soft agent preference, nullable, never hides a task.
- ``created_by``: who filed the task, nullable, informational.

Plus a composite index on (project_id, status, priority) for the board and
get_next_task queries.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Same checkfirst pattern as 0001: table drops don't drop enum types, so a
    # downgrade/upgrade round-trip would fail on CREATE TYPE without this.
    task_priority_enum = postgresql.ENUM(
        "critical", "high", "medium", "low",
        name="taskpriority", create_type=False,
    )
    task_priority_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "task",
        sa.Column(
            "priority",
            task_priority_enum,
            nullable=False,
            server_default="medium",
        ),
    )
    op.add_column(
        "task",
        sa.Column("preferred_model", sa.String(), nullable=True),
    )
    op.add_column(
        "task",
        sa.Column("created_by", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_task_project_status_priority",
        "task",
        ["project_id", "status", "priority"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_task_project_status_priority", table_name="task")
    op.drop_column("task", "created_by")
    op.drop_column("task", "preferred_model")
    op.drop_column("task", "priority")
    sa.Enum(name="taskpriority").drop(op.get_bind(), checkfirst=True)
