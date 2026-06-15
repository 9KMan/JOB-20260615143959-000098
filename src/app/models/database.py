# src/app/models/database.py
"""
Database Configuration and Session Management.
Async SQLAlchemy engine and session factory with connection pooling.
"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool

from app.core.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""
    pass


# Create async engine with connection pooling
if settings.DEBUG:
    # Use NullPool for debugging to avoid connection issues
    _engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        poolclass=NullPool,
        pool_pre_ping=True,
    )
else:
    # Production: Use AsyncAdaptedQueuePool with proper sizing
    _engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        poolclass=AsyncAdaptedQueuePool,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        pool_pre_ping=True,
        pool_recycle=3600,
        pool_timeout=30,
    )


engine: AsyncEngine = _engine

# Session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def create_tables() -> None:
    """Create all database tables."""
    async with engine.begin() as conn:
        # Import models to register them with Base
        from app.models import models  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)


async def drop_tables() -> None:
    """Drop all database tables (use with caution!)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session with automatic cleanup."""
    session = async_session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database session."""
    async with get_session() as session:
        yield session


async def check_database_health() -> dict[str, bool]:
    """Check database connectivity and pool health."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"connected": True, "pool_healthy": True}
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {"connected": False, "pool_healthy": False, "error": str(e)}


async def get_pool_status() -> dict[str, int]:
    """Get current connection pool status."""
    pool = engine.pool
    return {
        "pool_size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "invalid": pool.invalidatedcount() if hasattr(pool, "invalidatedcount") else 0,
    }
