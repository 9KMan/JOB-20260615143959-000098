// src/models/__init__.py
"""SQLAlchemy models for the scraping platform."""
from .base import Base, get_engine, get_session, init_db
from .batch import Batch, BatchStatus
from .job import Job, JobStatus, JobError
from .result import Result
from .error_log import ErrorLog, ErrorCategory
from .proxy_state import ProxyState, ProxyStatus

__all__ = [
    "Base",
    "get_engine",
    "get_session",
    "init_db",
    "Batch",
    "BatchStatus",
    "Job",
    "JobStatus",
    "JobError",
    "Result",
    "ErrorLog",
    "ErrorCategory",
    "ProxyState",
    "ProxyStatus",
]
