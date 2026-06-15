# =============================================================================
# Database Connection and Session Management
# =============================================================================

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool, QueuePool

from scraper.config import settings

logger = logging.getLogger(__name__)

# Create async engine
_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def create_engine() -> AsyncEngine:
    """Create async database engine with proper pooling."""
    engine_config = {
        "url": settings.database.url,
        "echo": settings.database.echo,
        "poolclass": QueuePool,
        "pool_size": settings.database.pool_size,
        "max_overflow": settings.database.max_overflow,
        "pool_timeout": settings.database.pool_timeout,
        "pool_recycle": settings.database.pool_recycle,
        "pool_pre_ping": True,  # Enable connection health checks
    }
    
    # Use NullPool in production for better connection management
    if settings.is_production:
        engine_config["poolclass"] = NullPool
    
    return create_async_engine(**engine_config)


async def init_db() -> None:
    """Initialize database connection."""
    global _engine, _async_session_factory
    
    logger.info("Initializing database connection...")
    
    _engine = create_engine()
    
    _async_session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    
    # Test connection
    async with _engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    
    logger.info("Database connection initialized successfully")


async def close_db() -> None:
    """Close database connection."""
    global _engine, _async_session_factory
    
    if _engine:
        logger.info("Closing database connection...")
        await _engine.dispose()
        _engine = None
        _async_session_factory = None
        logger.info("Database connection closed")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session."""
    if _async_session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    
    async with _async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_session_context() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session as context manager."""
    if _async_session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    
    async with _async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_engine() -> AsyncEngine:
    """Get database engine instance."""
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _engine
