// models/__init__.py
"""SQLAlchemy models for the scraping framework.

This package contains all database models with async support.
Uses UUID primary keys, JSONB for flexible metadata, and proper
indexing for high-throughput worker operations.
"""
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase
import uuid

from models.enums import (
    JobStatus,
    TaskStatus,
    CircuitState,
    FailureCategory,
    ProxyStatus,
    WorkerStatus,
    classify_error,
    TERMINAL_ERRORS,
    TRANSIENT_ERRORS,
)


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all models with async support."""
    pass


def generate_uuid() -> uuid.UUID:
    """Generate a new UUID for primary keys."""
    return uuid.uuid4()


# Import all models to make them available via `from models import *`
from models.job import Job
from models.scrape_task import ScrapeTask
from models.result import ScrapeResult
from models.failure import ScrapeFailure
from models.proxy_session import ProxySession
from models.worker import WorkerInstance

__all__ = [
    "Base",
    "Job",
    "ScrapeTask",
    "ScrapeResult",
    "ScrapeFailure",
    "ProxySession",
    "WorkerInstance",
    "JobStatus",
    "TaskStatus",
    "CircuitState",
    "FailureCategory",
    "ProxyStatus",
    "WorkerStatus",
    "classify_error",
    "TERMINAL_ERRORS",
    "TRANSIENT_ERRORS",
    "generate_uuid",
]
