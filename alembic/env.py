// alembic/env.py
"""Alembic migration environment configuration.

Configures async SQLAlchemy engine for use with Alembic migrations.
Supports both async and sync migration operations.
"""
import asyncio
from logging.config import fileConfig
from typing import AsyncGenerator

from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from alembic import context

# Import models and base for autogenerate support
from models import Base
from models.enums import (
    JobStatus,
    TaskStatus,
    CircuitState,
    FailureCategory,
    ProxyStatus,
    WorkerStatus,
)

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata for autogenerate
target_metadata = Base.metadata


def get_url() -> str:
    """Get database URL from config or environment.
    
    Supports both direct config and environment variable override.
    """
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    
    # Build URL from environment variables
    import os
    
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")
    db = os.getenv("POSTGRES_DB", "scraper")
    
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.
    
    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well. By skipping the Engine creation
    we don't even need a DBAPI to be available.
    
    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with the given connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in async mode."""
    connectable = create_async_engine(
        get_url(),
        poolclass=pool.NullPool,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
    )

    async with connectable.connect() as connection:
        await connection.execute(text("SET search_path TO public"))
        await connection.commit()
        
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
