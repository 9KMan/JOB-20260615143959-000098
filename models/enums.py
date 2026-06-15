"""Enum definitions mapped to PostgreSQL ENUM types."""
import enum


class JobStatus(str, enum.Enum):
    """Status of a scraping job/batch."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskStatus(str, enum.Enum):
    """Status of a scraping task within a job."""
    PENDING = "pending"
    CLAIMED = "claimed"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class CircuitState(str, enum.Enum):
    """Circuit breaker state for tasks and workers."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class FailureCategory(str, enum.Enum):
    """Category of a scrape failure."""
    TRANSIENT = "transient"
    TERMINAL = "terminal"
    UNKNOWN = "unknown"


class ProxyStatus(str, enum.Enum):
    """Status of a proxy session."""
    ACTIVE = "active"
    EXHAUSTED = "exhausted"
    ERROR = "error"
    RETIRED = "retired"


class WorkerStatus(str, enum.Enum):
    """Status of a worker instance."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"


# Terminal errors that should not be retried
TERMINAL_ERROR_CODES = frozenset([
    "HTTP_403",
    "HTTP_451",
    "PERMANENT_BLOCK",
    "ACCOUNT_LOCKED",
    "SITE_BLOCKED",
])

# Transient errors that may succeed on retry
TRANSIENT_ERROR_CODES = frozenset([
    "ERR_TUNNEL",
    "TIMEOUT",
    "RATE_LIMIT",
    "CONNECTION_RESET",
    "CONNECTION_REFUSED",
    "DNS_FAILURE",
    "PROXY_AUTH_FAILED",
    "SESSION_EXPIRED",
])

# Error codes that may indicate anti-bot measures
ANTI_BOT_ERROR_CODES = frozenset([
    "CAPTCHA",
    "ANTI_BOT",
    "HEADLESS_DETECTED",
    "CLOUDFLARE_BLOCK",
    "INCAPSULA_BLOCK",
])

# Default retry policies configuration
DEFAULT_RETRY_POLICIES = {
    "ERR_TUNNEL": {
        "base_delay_seconds": 30,
        "max_delay_seconds": 3600,
        "multiplier": 2.0,
        "max_attempts": 5,
    },
    "TIMEOUT": {
        "base_delay_seconds": 10,
        "max_delay_seconds": 300,
        "multiplier": 1.5,
        "max_attempts": 5,
    },
    "CAPTCHA": {
        "base_delay_seconds": 60,
        "max_delay_seconds": 1800,
        "multiplier": 2.0,
        "max_attempts": 3,
    },
    "ANTI_BOT": {
        "base_delay_seconds": 120,
        "max_delay_seconds": 3600,
        "multiplier": 2.0,
        "max_attempts": 3,
    },
    "RATE_LIMIT": {
        "base_delay_seconds": 60,
        "max_delay_seconds": 1800,
        "multiplier": 1.5,
        "max_attempts": 5,
    },
    "CONNECTION_RESET": {
        "base_delay_seconds": 5,
        "max_delay_seconds": 120,
        "multiplier": 2.0,
        "max_attempts": 5,
    },
    "TRANSIENT": {
        "base_delay_seconds": 10,
        "max_delay_seconds": 300,
        "multiplier": 1.5,
        "max_attempts": 3,
    },
    "UNKNOWN": {
        "base_delay_seconds": 30,
        "max_delay_seconds": 600,
        "multiplier": 2.0,
        "max_attempts": 3,
    },
}


def classify_error_code(error_code: str) -> FailureCategory:
    """Classify an error code into transient/terminal/unknown category."""
    upper_code = error_code.upper()
    if upper_code in TERMINAL_ERROR_CODES:
        return FailureCategory.TERMINAL
    if upper_code in TRANSIENT_ERROR_CODES or upper_code in ANTI_BOT_ERROR_CODES:
        return FailureCategory.TRANSIENT
    return FailureCategory.UNKNOWN
