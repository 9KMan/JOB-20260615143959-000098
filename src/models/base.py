// src/models/base.py
"""Base model configuration and database connection management."""
import os
from typing import Generator, Optional
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from sqlalchemy.pool import NullPool, QueuePool

from src.core.config import get_settings


Base = declarative_base()


def get_engine():
    """Create SQLAlchemy engine based on configuration."""
    settings = get_settings()
    
    engine = create_engine(
        settings.database.url,
        poolclass=QueuePool,
        pool_size=settings.database.pool_size,
        max_overflow=settings.database.max_overflow,
        pool_timeout=settings.database.pool_timeout,
        pool_pre_ping=True,
        echo=settings.database.echo,
    )
    
    return engine


def get_session_factory():
    """Get SQLAlchemy session factory."""
    engine = get_engine()
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Global session factory
_session_factory: Optional[sessionmaker] = None


def get_session_factory_singleton():
    """Get cached session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = get_session_factory()
    return _session_factory


def get_session() -> Generator[Session, None, None]:
    """Get a database session (generator for dependency injection)."""
    session_factory = get_session_factory_singleton()
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def get_session_context() -> Generator[Session, None, None]:
    """Get a database session as a context manager."""
    session_factory = get_session_factory_singleton()
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db():
    """Initialize database tables."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


def drop_db():
    """Drop all database tables."""
    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
