"""phase6: task.assigned_to column + index

Revision ID: a1b2c3d4e5f6
Revises: 6ea6c5f74f49
Create Date: 2026-07-07 08:00:00.000000

Adds an indexed ``assigned_to`` column to the ``task`` table. When set, the
task is reserved for the named agent: only that agent sees it in
get_next_task / list_tasks and can claim it. Nullable — most tasks are
unassigned (visible to all agents).
"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel  # noqa: F401  (autogenerate emits sqlmodel.sql.sqltypes.AutoString)
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "6ea6c5f74f49"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "task",
        sa.Column(
            "assigned_to",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
    )
    op.create_index(op.f("ix_task_assigned_to"), "task", ["assigned_to"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_task_assigned_to"), table_name="task")
    op.drop_column("task", "assigned_to")
