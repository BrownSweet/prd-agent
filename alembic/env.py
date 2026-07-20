from __future__ import annotations

from logging.config import fileConfig
import os
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url

from prd_agent.repositories import Base
from prd_agent.settings import validate_database_url

config = context.config

configured_url = config.get_main_option("sqlalchemy.url")
if not configured_url and (database_url := os.getenv("DATABASE_URL")):
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    configured_url = config.get_main_option("sqlalchemy.url")
if not configured_url:
    raise RuntimeError("缺少 DATABASE_URL，无法运行数据库迁移")
url = make_url(configured_url)
try:
    validate_database_url(configured_url)
except ValueError as exc:
    raise RuntimeError(str(exc)) from exc
if url.get_backend_name() == "sqlite" and url.database != ":memory:":
    Path(url.database or "").expanduser().resolve().parent.mkdir(
        parents=True,
        exist_ok=True,
    )

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    migration_url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=migration_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=url.get_backend_name() == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    if url.get_backend_name() == "mysql":
        connect_args = {
            "connect_timeout": int(
                os.getenv("DATABASE_CONNECT_TIMEOUT_SECONDS", "5")
            ),
            "read_timeout": int(
                os.getenv("DATABASE_READ_TIMEOUT_SECONDS", "30")
            ),
            "write_timeout": int(
                os.getenv("DATABASE_READ_TIMEOUT_SECONDS", "30")
            ),
        }
    else:
        connect_args = {
            "timeout": int(os.getenv("DATABASE_READ_TIMEOUT_SECONDS", "30")),
        }
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )
    with connectable.connect() as connection:
        if url.get_backend_name() == "sqlite":
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.exec_driver_sql("PRAGMA journal_mode=WAL")
            connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=url.get_backend_name() == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
