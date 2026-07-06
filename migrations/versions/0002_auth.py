"""auth: users and tokens tables

Revision ID: a6922274af5d
Revises: acf3da774aa4
Create Date: 2026-07-06 18:25:36.457685

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401  (autogenerate emits sqlmodel.sql.sqltypes.AutoString)

# revision identifiers, used by Alembic.
revision: str = 'a6922274af5d'
down_revision: Union[str, Sequence[str], None] = 'acf3da774aa4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('user',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('password_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('is_admin', sa.Boolean(), nullable=False, server_default=sa.text("false")),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_username'), 'user', ['username'], unique=True)
    op.create_table('token',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('agent_name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('token_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('created_by_user_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('last_used_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_token_agent_name'), 'token', ['agent_name'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_token_agent_name'), table_name='token')
    op.drop_table('token')
    op.drop_index(op.f('ix_user_username'), table_name='user')
    op.drop_table('user')
