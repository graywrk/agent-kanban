"""Alembic env. Reads DATABASE_URL, imports SQLModel.metadata.

Alembic runs synchronously via psycopg2 (the +asyncpg driver is stripped).
This lets `command.upgrade()` be invoked from within a running event loop,
which the pytest fixtures in conftest.py do.
"""
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

import agent_kanban.models  # noqa: F401  (register tables on metadata)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override url from env if present. Strip the asyncpg driver so alembic uses
# the sync psycopg2 driver.
db_url = os.environ.get("DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url.replace("+asyncpg", ""))

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
