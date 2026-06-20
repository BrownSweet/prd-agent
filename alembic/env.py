from __future__ import annotations

from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url

from prd_agent.repositories import Base

config = context.config

configured_url = config.get_main_option("sqlalchemy.url")
if not configured_url and (database_url := os.getenv("DATABASE_URL")):
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    configured_url = config.get_main_option("sqlalchemy.url")
if not configured_url:
    raise RuntimeError("缺少 DATABASE_URL，无法运行数据库迁移")
url = make_url(configured_url)
if url.get_backend_name() != "mysql" or url.drivername != "mysql+pymysql":
    raise RuntimeError("数据库迁移仅支持 mysql+pymysql")
if url.query.get("charset") != "utf8mb4":
    raise RuntimeError("MySQL连接必须包含 charset=utf8mb4")

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


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


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={
            "connect_timeout": int(
                os.getenv("DATABASE_CONNECT_TIMEOUT_SECONDS", "5")
            ),
            "read_timeout": int(
                os.getenv("DATABASE_READ_TIMEOUT_SECONDS", "30")
            ),
            "write_timeout": int(
                os.getenv("DATABASE_READ_TIMEOUT_SECONDS", "30")
            ),
        },
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
