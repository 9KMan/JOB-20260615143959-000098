# src/app/core/exceptions.py
"""
Custom Exception Classes.
Defines application-specific exceptions for different failure modes.
"""
from typing import Any, Optional


class ScrapingBaseException(Exception):
    """Base exception for all scraping-related errors."""
    
    def __init__(
        self,
        message: str,
        details: Optional[dict[str, Any]] = None,
        retryable: bool = True,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.retryable = retryable


# Proxy-related exceptions
class ProxyError(ScrapingBaseException):
    """Base class for proxy-related errors."""
    
    def __init__(
        self,
        message: str,
        proxy_url: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.proxy_url = proxy_url


class ProxyTunnelError(ProxyError):
    """ERR_TUNNEL or connection tunnel error through proxy."""
    
    def __init__(self, message: str = "Proxy tunnel error", **kwargs: Any) -> None:
        super().__init__(message, retryable=True, **kwargs)


class ProxyAuthenticationError(ProxyError):
    """Proxy authentication failed."""
    
    def __init__(self, message: str = "Proxy authentication failed", **kwargs: Any) -> None:
        super().__init__(message, retryable=False, **kwargs)


class ProxyTimeoutError(ProxyError):
    """Proxy request timed out."""
    
    def __init__(self, message: str = "Proxy request timed out", **kwargs: Any) -> None:
        super().__init__(message, retryable=True, **kwargs)


class ProxyHealthError(ProxyError):
    """Proxy health check failed - proxy marked as unhealthy."""
    
    def __init__(
        self,
        message: str = "Proxy health check failed",
        failure_count: int = 0,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, retryable=True, **kwargs)
        self.failure_count = failure_count


# Anti-bot detection exceptions
class AntiBotError(ScrapingBaseException):
    """Base class for anti-bot detection errors."""
    
    def __init__(
        self,
        message: str,
        detection_type: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, retryable=True, **kwargs)
        self.detection_type = detection_type


class CaptchaError(AntiBotError):
    """Captcha challenge detected."""
    
    def __init__(
        self,
        message: str = "Captcha challenge detected",
        captcha_type: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, detection_type="captcha", **kwargs)
        self.captcha_type = captcha_type


class CookieConsentError(AntiBotError):
    """Cookie consent banner blocking content."""
    
    def __init__(
        self,
        message: str = "Cookie consent banner blocking content",
        **kwargs: Any,
    ) -> None:
        super().__init__(message, detection_type="cookie_consent", **kwargs)


class HeadlessDetectionError(AntiBotError):
    """Headless browser detected by target site."""
    
    def __init__(
        self,
        message: str = "Headless browser detected",
        **kwargs: Any,
    ) -> None:
        super().__init__(message, detection_type="headless_detection", **kwargs)


class RateLimitError(AntiBotError):
    """Rate limiting applied by target site."""
    
    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, detection_type="rate_limit", **kwargs)
        self.retry_after = retry_after


# Navigation/Rendering exceptions
class NavigationError(ScrapingBaseException):
    """Base class for page navigation errors."""
    
    def __init__(
        self,
        message: str,
        url: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, retryable=True, **kwargs)
        self.url = url


class PageLoadTimeoutError(NavigationError):
    """Page load timed out."""
    
    def __init__(
        self,
        message: str = "Page load timed out",
        timeout_ms: int = 0,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, retryable=True, **kwargs)
        self.timeout_ms = timeout_ms


class StaleElementError(NavigationError):
    """DOM element became stale during interaction."""
    
    def __init__(self, message: str = "DOM element became stale", **kwargs: Any) -> None:
        super().__init__(message, retryable=True, **kwargs)


class XvfbError(ScrapingBaseException):
    """Xvfb display server error."""
    
    def __init__(
        self,
        message: str = "Xvfb display error",
        display: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, retryable=True, **kwargs)
        self.display = display


# Terminal (non-retryable) exceptions
class TerminalError(ScrapingBaseException):
    """Base class for terminal (non-retryable) errors."""
    
    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, retryable=False, **kwargs)


class SiteNotFoundError(TerminalError):
    """Target site does not exist or URL is invalid."""
    
    def __init__(self, message: str = "Target site not found", url: str = "") -> None:
        super().__init__(message)
        self.url = url


class SiteAccessDeniedError(TerminalError):
    """Access denied by target site (e.g., IP ban)."""
    
    def __init__(self, message: str = "Access denied", url: str = "") -> None:
        super().__init__(message)
        self.url = url


class ContentUnavailableError(TerminalError):
    """Content is permanently unavailable (404,410,etc)."""
    
    def __init__(
        self,
        message: str = "Content permanently unavailable",
        status_code: int = 0,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, retryable=False, **kwargs)
        self.status_code = status_code


class InvalidSelectorError(TerminalError):
    """CSS/XPath selector is invalid or cannot find element."""
    
    def __init__(self, message: str = "Invalid or missing selector", selector: str = "") -> None:
        super().__init__(message)
        self.selector = selector


# Worker/Fleet exceptions
class WorkerError(ScrapingBaseException):
    """Base class for worker-related errors."""
    
    def __init__(self, message: str, worker_id: Optional[str] = None, **kwargs: Any) -> None:
        super().__init__(message, retryable=False, **kwargs)
        self.worker_id = worker_id


class CircuitBreakerOpenError(WorkerError):
    """Circuit breaker is open, rejecting requests."""
    
    def __init__(
        self,
        message: str = "Circuit breaker is open",
        circuit_name: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.circuit_name = circuit_name


class QueueFullError(WorkerError):
    """Worker queue is full, cannot accept more jobs."""
    
    def __init__(self, message: str = "Queue is full", **kwargs: Any) -> None:
        super().__init__(message, retryable=True, **kwargs)


# Classification exceptions
class ClassificationError(ScrapingBaseException):
    """Error during failure classification."""
    
    def __init__(self, message: str, job_id: str = "") -> None:
        super().__init__(message, retryable=False)
        self.job_id = job_id


class AmbiguousError(ClassificationError):
    """Error could not be unambiguously classified."""
    
    def __init__(
        self,
        message: str = "Error classification ambiguous",
        job_id: str = "",
        error_types: list[str] = None,
    ) -> None:
        super().__init__(message, job_id)
        self.error_types = error_types or []


# Recovery exceptions
class RecoveryError(ScrapingBaseException):
    """Error during recovery attempt."""
    
    def __init__(self, message: str, job_id: str = "", **kwargs: Any) -> None:
        super().__init__(message, retryable=True, **kwargs)
        self.job_id = job_id


class MaxRetriesExceededError(RecoveryError):
    """Maximum retry attempts exceeded."""
    
    def __init__(
        self,
        message: str = "Maximum retries exceeded",
        job_id: str = "",
        retry_count: int = 0,
    ) -> None:
        super().__init__(message, job_id, retryable=False)
        self.retry_count = retry_count


# LLM exceptions
class LLMError(ScrapingBaseException):
    """Base class for LLM-related errors."""
    
    def __init__(
        self,
        message: str,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, retryable=True, **kwargs)
        self.model = model


class LLMRateLimitError(LLMError):
    """LLM rate limit exceeded."""
    
    def __init__(
        self,
        message: str = "LLM rate limit exceeded",
        retry_after: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class LLMCostLimitError(LLMError):
    """LLM cost limit exceeded."""
    
    def __init__(
        self,
        message: str = "LLM cost limit exceeded",
        current_cost: float = 0.0,
        limit: float = 0.0,
    ) -> None:
        super().__init__(message, retryable=False)
        self.current_cost = current_cost
        self.limit = limit


# Database exceptions
class DatabaseError(ScrapingBaseException):
    """Base class for database errors."""
    
    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, retryable=True, **kwargs)
