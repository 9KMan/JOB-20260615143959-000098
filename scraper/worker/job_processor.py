# =============================================================================
# Job Processor
# Handles the actual scraping logic with retry, circuit breaker, and proxy management
# =============================================================================

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
import structlog
from circuitbreaker import circuit
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_random,
)

from scraper.config import settings
from scraper.proxy_manager import ProxyManager

logger = structlog.get_logger(__name__)


class ProxyError(Exception):
    """Raised when a proxy-related error occurs."""
    pass


class TunnelTimeoutError(ProxyError):
    """Raised when proxy tunnel times out."""
    pass


class ProxyAuthError(ProxyError):
    """Raised when proxy authentication fails."""
    pass


class ProxyThrottleError(ProxyError):
    """Raised when proxy is throttled."""
    pass


@dataclass
class ScrapedContent:
    """Container for scraped content."""
    url: str
    status_code: int
    headers: Dict[str, str]
    content: str
    content_type: str
    response_time_ms: int
    proxy_used: str
    cookies: Dict[str, str] = field(default_factory=dict)
    screenshot: Optional[bytes] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class JobResult:
    """Result of a scraping job."""
    job_id: str
    success: bool
    content: Optional[ScrapedContent] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    retryable: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


class JobProcessor:
    """Processes scraping jobs with proxy rotation and retry logic."""
    
    # HTTP status codes that indicate retryable errors
    RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
    
    # Error messages that indicate retryable proxy errors
    PROXY_ERROR_PATTERNS = [
        "ERR_TUNNEL_CONNECTION_TIMED_OUT",
        "ERR_TUNNEL_CONNECTION_FAILED",
        "407",
        "429",
        "timeout",
        "connection refused",
    ]
    
    def __init__(self, proxy_manager: Optional[ProxyManager] = None):
        self.proxy_manager = proxy_manager or ProxyManager()
        self._session_cookies: Dict[str, Dict[str, str]] = {}
    
    def _is_retryable_error(self, error: Exception) -> bool:
        """Determine if an error is retryable."""
        error_str = str(error).lower()
        
        for pattern in self.PROXY_ERROR_PATTERNS:
            if pattern.lower() in error_str:
                return True
        
        return False
    
    def _classify_error(self, error: Exception) -> tuple[str, bool]:
        """Classify error and determine if retryable."""
        error_str = str(error)
        
        if isinstance(error, TunnelTimeoutError):
            return "TUNNEL_TIMEOUT", True
        elif isinstance(error, ProxyAuthError):
            return "PROXY_AUTH", False
        elif isinstance(error, ProxyThrottleError):
            return "PROXY_THROTTLE", True
        elif isinstance(error, ProxyError):
            return "PROXY_ERROR", True
        elif "407" in error_str:
            return "PROXY_AUTH", False
        elif "timeout" in error_str.lower():
            return "TIMEOUT", True
        elif "connection" in error_str.lower():
            return "CONNECTION_ERROR", True
        
        return "UNKNOWN", True
    
    @circuit(
        failure_threshold=settings.circuit_breaker.failure_threshold,
        recovery_timeout=settings.circuit_breaker.recovery_timeout,
        half_open_max_calls=settings.circuit_breaker.half_open_max_calls,
        excluded_exception=ProxyAuthError,
    )
    async def _make_request_with_proxy(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None,
        post_data: Optional[str] = None,
        country_code: str = "US",
        session_id: Optional[str] = None,
    ) -> ScrapedContent:
        """Make HTTP request with proxy rotation."""
        proxy = await self.proxy_manager.get_proxy(
            country_code=country_code,
            session_id=session_id,
        )
        
        start_time = time.time()
        
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=settings.worker.page_load_timeout,
                    write=10.0,
                    pool=30.0,
                ),
                follow_redirects=True,
                max_redirects=10,
            ) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    cookies=cookies,
                    content=post_data,
                    proxy=proxy.format_url(),
                )
                
                response_time_ms = int((time.time() - start_time) * 1000)
                
                # Check for throttling
                if response.status_code == 429:
                    raise ProxyThrottleError("Proxy throttled with 429")
                
                # Get response content
                content = response.text
                
                return ScrapedContent(
                    url=str(response.url),
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    content=content,
                    content_type=response.headers.get("content-type", ""),
                    response_time_ms=response_time_ms,
                    proxy_used=proxy.address,
                    cookies=dict(response.cookies),
                )
                
        except httpx.ProxyError as e:
            error_str = str(e)
            
            if "407" in error_str or "authentication" in error_str.lower():
                await self.proxy_manager.mark_proxy_failed(proxy, "AUTH_FAILED")
                raise ProxyAuthError(f"Proxy authentication failed: {error_str}")
            elif "timeout" in error_str.lower() or "timed out" in error_str.lower():
                await self.proxy_manager.mark_proxy_failed(proxy, "TUNNEL_TIMEOUT")
                raise TunnelTimeoutError(f"Tunnel timeout: {error_str}")
            else:
                await self.proxy_manager.mark_proxy_failed(proxy, "CONNECTION_ERROR")
                raise ProxyError(f"Proxy connection error: {error_str}")
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code in self.RETRYABLE_STATUS_CODES:
                raise
            raise
    
    async def process_job(self, job_data: Dict[str, Any]) -> JobResult:
        """Process a scraping job."""
        job_id = job_data.get("id", "unknown")
        
        structlog.contextvars.bind_contextvars(job_id=job_id)
        logger.info("Processing job", job_id=job_id, url=job_data.get("url"))
        
        retry_count = job_data.get("retry_count", 0)
        max_retries = job_data.get("max_retries", settings.worker.max_retries)
        
        for attempt in range(max_retries + 1):
            try:
                # Make request with retry logic
                content = await self._attempt_scrape(job_data)
                
                return JobResult(
                    job_id=job_id,
                    success=True,
                    content=content,
                    metadata={
                        "attempts": attempt + 1,
                        "proxy_used": content.proxy_used,
                    },
                )
                
            except ProxyAuthError as e:
                # Non-retryable, fail immediately
                error_type, retryable = self._classify_error(e)
                return JobResult(
                    job_id=job_id,
                    success=False,
                    error=str(e),
                    error_type=error_type,
                    retryable=False,
                    metadata={"attempts": attempt + 1},
                )
                
            except Exception as e:
                error_type, retryable = self._classify_error(e)
                logger.warning(
                    "Attempt failed",
                    attempt=attempt + 1,
                    error=str(e),
                    error_type=error_type,
                )
                
                if attempt >= max_retries or not retryable:
                    return JobResult(
                        job_id=job_id,
                        success=False,
                        error=str(e),
                        error_type=error_type,
                        retryable=retryable,
                        metadata={"attempts": attempt + 1},
                    )
                
                # Wait before retry with exponential backoff
                wait_time = settings.worker.retry_delay * (2 ** attempt)
                wait_time += wait_random(0, 5)
                await asyncio.sleep(wait_time)
        
        return JobResult(
            job_id=job_id,
            success=False,
            error="Max retries exceeded",
            error_type="MAX_RETRIES",
            retryable=False,
        )
    
    async def _attempt_scrape(self, job_data: Dict[str, Any]) -> ScrapedContent:
        """Attempt a single scrape."""
        url = job_data["url"]
        method = job_data.get("method", "GET")
        headers = job_data.get("headers", {})
        cookies = job_data.get("cookies", {})
        post_data = job_data.get("post_data")
        country_code = job_data.get("country_code", "US")
        session_id = job_data.get("session_id")
        
        return await self._make_request_with_proxy(
            url=url,
            method=method,
            headers=headers,
            cookies=cookies,
            post_data=post_data,
            country_code=country_code,
            session_id=session_id,
        )
