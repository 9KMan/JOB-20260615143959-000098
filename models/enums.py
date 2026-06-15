// models/enums.py
"""PostgreSQL enum types for the scraping framework.

These enums are created as PostgreSQL types via Alembic migration.
SQLAlchemy uses these as TypeEngine decorators.
"""
from enum import Enum


class JobStatus(str, Enum):
    """Status of a scraping job/batch."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskStatus(str, Enum):
    """Status of an individual scrape task."""
    PENDING = "pending"
    CLAIMED = "claimed"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class CircuitState(str, Enum):
    """Circuit breaker state for tasks and workers."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class FailureCategory(str, Enum):
    """Classification of failure types."""
    TRANSIENT = "transient"
    TERMINAL = "terminal"
    UNKNOWN = "unknown"


class ProxyStatus(str, Enum):
    """Status of a proxy session."""
    ACTIVE = "active"
    EXHAUSTED = "exhausted"
    ERROR = "error"
    RETIRED = "retired"


class WorkerStatus(str, Enum):
    """Status of a worker instance."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"


# Error code constants for classification
TERMINAL_ERRORS = frozenset([
    "HTTP_403",
    "HTTP_451",
    "PERMANENT_BLOCK",
    "ACCOUNT_LOCKED",
    "CLOUDFLARE_BLOCK",
    "DATADOME_BLOCK",
])

TRANSIENT_ERRORS = frozenset([
    "ERR_TUNNEL",
    "TIMEOUT",
    "RATE_LIMIT",
    "CONNECTION_RESET",
    "CONNECTION_REFUSED",
    "CONNECTION_TIMEOUT",
    "SSL_ERROR",
    "NETWORK_ERROR",
    "PROXY_AUTH_FAILED",
    "TUNNEL_ERROR",
])


def classify_error(error_code: str) -> FailureCategory:
    """Classify an error code as transient, terminal, or unknown.
    
    Args:
        error_code: The error code string to classify.
        
    Returns:
        FailureCategory enum value.
    """
    if error_code in TERMINAL_ERRORS:
        return FailureCategory.TERMINAL
    elif error_code in TRANSIENT_ERRORS:
        return FailureCategory.TRANSIENT
    else:
        return FailureCategory.UNKNOWN
