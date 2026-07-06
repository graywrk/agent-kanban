"""phase5: token_prefix column + index

Revision ID: 6ea6c5f74f49
Revises: a6922274af5d
Create Date: 2026-07-06 20:38:56.843737

Adds an indexed ``token_prefix`` column (first 8 chars of the plaintext token)
to the ``token`` table so bearer lookup is O(1) index + 1 bcrypt verify instead
of an O(N) bcrypt scan.
"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel  # noqa: F401  (autogenerate emits sqlmodel.sql.sqltypes.AutoString)
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6ea6c5f74f49"
down_revision: Union[str, Sequence[str], None] = "a6922274af5d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "token",
        sa.Column(
            "token_prefix",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="",
        ),
    )
    op.create_index(op.f("ix_token_token_prefix"), "token", ["token_prefix"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_token_token_prefix"), table_name="token")
    op.drop_column("token", "token_prefix")
