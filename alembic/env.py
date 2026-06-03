from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import *  # noqa: F401,F403

config = context.config
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_DB_CONNECT_MAX_ATTEMPTS = int(os.getenv("ALEMBIC_DB_CONNECT_MAX_ATTEMPTS", "30"))
_DB_CONNECT_RETRY_SECONDS = float(os.getenv("ALEMBIC_DB_CONNECT_RETRY_SECONDS", "1"))


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    try:
        last_error: OperationalError | OSError | None = None
        for attempt in range(1, _DB_CONNECT_MAX_ATTEMPTS + 1):
            try:
                async with connectable.connect() as connection:
                    await connection.run_sync(do_run_migrations)
                return
            except (OperationalError, OSError) as exc:
                last_error = exc
                if attempt >= _DB_CONNECT_MAX_ATTEMPTS:
                    raise
                print(
                    "[alembic] database is not reachable yet "
                    f"(attempt {attempt}/{_DB_CONNECT_MAX_ATTEMPTS}): {exc}"
                )
                await asyncio.sleep(_DB_CONNECT_RETRY_SECONDS)

        if last_error is not None:
            raise last_error
    finally:
        await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
