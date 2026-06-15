# src/scraper/scraper.py
"""Base scraper class with common functionality for all scrapers."""

import asyncio
import hashlib
import json
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Type
from urllib.parse import urljoin, urlparse

import yaml
from pydantic import BaseModel, Field

from src.config.settings import get_settings
from src.config.sites import SiteConfig
from src.scraper.browser import BrowserPool, BrowserContext, BrowserProfile
from src.scraper.page import PageHelper, CookieConsentType
from src.utils.logging import get_logger

logger = get_logger(__name__)


class ScraperStatus(Enum):
    """Scraper execution status."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"  # Some data extracted, some failed


class ErrorSeverity(Enum):
    """Error severity classification."""
    TRANSIENT = "transient"  # Can retry
    TERMINAL = "terminal"   # Will not succeed with retries
    UNKNOWN = "unknown"


@dataclass
class ExtractionResult:
    """Result of data extraction from a page."""
    url: str
    status: ScraperStatus
    data: Dict[str, Any] = field(default_factory=dict)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    extraction_time_ms: int = 0
    pages_scraped: int = 1
    retry_count: int = 0
    session_id: Optional[str] = None
    proxy_used: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "url": self.url,
            "status": self.status.value,
            "data": self.data,
            "errors": self.errors,
            "warnings": self.warnings,
            "metadata": self.metadata,
            "extraction_time_ms": self.extraction_time_ms,
            "pages_scraped": self.pages_scraped,
            "retry_count": self.retry_count,
            "session_id": self.session_id,
            "proxy_used": self.proxy_used,
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    @property
    def is_success(self) -> bool:
        """Check if extraction was successful."""
        return self.status in (ScraperStatus.SUCCESS, ScraperStatus.PARTIAL)
    
    @property
    def is_terminal_failure(self) -> bool:
        """Check if failure is terminal and should not be retried."""
        for error in self.errors:
            if error.get("severity") == ErrorSeverity.TERMINAL.value:
                return True
        return False
    
    def add_error(
        self,
        message: str,
        severity: ErrorSeverity = ErrorSeverity.UNKNOWN,
        page_url: Optional[str] = None,
        exception: Optional[Exception] = None,
    ) -> None:
        """Add an error to the result."""
        error_dict = {
            "message": message,
            "severity": severity.value,
            "timestamp": datetime.utcnow().isoformat(),
        }
        if page_url:
            error_dict["page_url"] = page_url
        if exception:
            error_dict["exception_type"] = type(exception).__name__
            error_dict["exception_message"] = str(exception)
        
        self.errors.append(error_dict)
    
    def add_warning(self, message: str) -> None:
        """Add a warning to the result."""
        self.warnings.append(message)


@dataclass
class JobInput:
    """Input for a scraping job."""
    job_id: str
    url: str
    site_name: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    callback_url: Optional[str] = None
    webhook_data: Optional[Dict[str, Any]] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JobInput":
        """Create from dictionary."""
        return cls(
            job_id=data.get("job_id", data.get("id", "")),
            url=data["url"],
            site_name=data.get("site_name", urlparse(data["url"]).netloc),
            parameters=data.get("parameters", {}),
            priority=data.get("priority", 0),
            callback_url=data.get("callback_url"),
            webhook_data=data.get("webhook_data"),
        )


class BaseScraper(ABC):
    """Base scraper class that all site-specific scrapers should extend.
    
    Provides:
    - Browser pool integration
    - Proxy management
    - Error handling and classification
    - Rate limiting
    - Site-specific configuration
    """
    
    # Override in subclass for site-specific settings
    site_name: str = "generic"
    default_timeout: int = 30000
    max_retries: int = 3
    
    def __init__(
        self,
        browser_pool: Optional[BrowserPool] = None,
        site_config: Optional[SiteConfig] = None,
        worker_id: Optional[str] = None,
    ):
        """Initialize base scraper.
        
        Args:
            browser_pool: Browser pool instance for context management
            site_config: Site-specific configuration
            worker_id: Worker identifier for logging
        """
        self.settings = get_settings()
        self.browser_pool = browser_pool or BrowserPool()
        self.site_config = site_config
        self.worker_id = worker_id or f"worker-{hashlib.md5(str(time.time()).encode()).hexdigest()[:8]}"
        
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._request_times: List[float] = []
        self._lock = asyncio.Lock()
    
    async def initialize(self) -> None:
        """Initialize browser pool and resources."""
        if not self.browser_pool._initialized:
            await self.browser_pool.initialize()
        
        # Set up rate limiting semaphore
        if self.site_config and self.site_config.rate_limit:
            requests_per_second = self.site_config.rate_limit
            self._semaphore = asyncio.Semaphore(int(requests_per_second))
        
        logger.info(
            f"Scraper initialized for {self.site_name} "
            f"(worker_id={self.worker_id})"
        )
    
    async def scrape(self, job: JobInput) -> ExtractionResult:
        """Execute scraping job.
        
        Args:
            job: Job input data
            
        Returns:
            Extraction result
        """
        start_time = time.time()
        result = ExtractionResult(
            url=job.url,
            status=ScraperStatus.PENDING,
            metadata={
                "job_id": job.job_id,
                "worker_id": self.worker_id,
                "site_name": job.site_name,
            }
        )
        
        # Apply rate limiting
        if self._semaphore:
            await self._semaphore.acquire()
            try:
                async with self._lock:
                    self._request_times.append(time.time())
                    # Clean old requests
                    cutoff = time.time() - 60
                    self._request_times = [
                        t for t in self._request_times if t > cutoff
                    ]
            finally:
                self._semaphore.release()
        
        # Get proxy for this job
        proxy = await self._get_proxy(job)
        if proxy:
            result.proxy_used = proxy.get("server", "")[:50]
        
        # Create browser profile for this site
        profile = self._create_profile(job)
        
        try:
            result.status = ScraperStatus.RUNNING
            
            # Create browser context
            async with self.browser_pool.acquire_context(
                profile=profile,
                proxy=proxy,
            ) as context_wrapper:
                page = await context_wrapper.context.new_page()
                
                try:
                    # Set up page helper
                    page_helper = PageHelper(page)
                    
                    # Navigate to target
                    nav_result = await page_helper.navigate_with_retry(
                        job.url,
                        timeout_ms=self.default_timeout,
                    )
                    
                    if not nav_result.success:
                        result.add_error(
                            f"Navigation failed: {nav_result.error}",
                            severity=ErrorSeverity.TRANSIENT,
                        )
                        result.status = ScraperStatus.FAILED
                        return result
                    
                    # Handle cookie consent
                    cookies_accepted, consent_type = await page_helper.handle_cookie_consent()
                    if cookies_accepted:
                        result.add_warning(f"Cookie consent handled: {consent_type}")
                    
                    # Wait for render
                    await page_helper.wait_for_render()
                    
                    # Site-specific extraction
                    site_result = await self.extract(page, page_helper, job)
                    result.data = site_result.data
                    result.warnings.extend(site_result.warnings)
                    result.pages_scraped = site_result.pages_scraped
                    
                    # Classify any errors
                    await self._classify_errors(result)
                    
                    # Determine final status
                    if result.errors and not result.data:
                        result.status = ScraperStatus.FAILED
                    elif result.errors and result.data:
                        result.status = ScraperStatus.PARTIAL
                    else:
                        result.status = ScraperStatus.SUCCESS
                    
                finally:
                    await page.close()
                    context_wrapper.increment_requests()
        
        except Exception as e:
            result.add_error(
                f"Scraping exception: {str(e)}",
                severity=ErrorSeverity.UNKNOWN,
                exception=e,
            )
            result.status = ScraperStatus.FAILED
            logger.exception(f"Scraping error for {job.url}")
        
        finally:
            result.extraction_time_ms = int((time.time() - start_time) * 1000)
        
        logger.info(
            f"Scraped {job.url} "
            f"(status={result.status.value}, time={result.extraction_time_ms}ms)"
        )
        
        return result
    
    @abstractmethod
    async def extract(
        self,
        page: Any,
        page_helper: PageHelper,
        job: JobInput,
    ) -> ExtractionResult:
        """Extract data from page. Must be implemented by subclass.
        
        Args:
            page: Playwright page
            page_helper: Page helper instance
            job: Job input
            
        Returns:
            Extraction result with data
        """
        pass
    
    async def _get_proxy(self, job: JobInput) -> Optional[Dict[str, str]]:
        """Get proxy for job. Override for custom proxy logic."""
        # Default implementation returns None (direct connection)
        # Subclasses or proxy rotator will provide actual proxy
        return None
    
    def _create_profile(self, job: JobInput) -> BrowserProfile:
        """Create browser profile for job.
        
        Override in subclass for site-specific profiles.
        """
        if self.site_config and self.site_config.default_profile:
            return self.site_config.default_profile
        
        return BrowserProfile(
            locale=self.site_config.default_locale if self.site_config else "en-US",
            timezone_id=self.site_config.default_timezone if self.site_config else "America/New_York",
        )
    
    async def _classify_errors(self, result: ExtractionResult) -> None:
        """Classify errors as transient or terminal.
        
        Override for custom classification logic.
        """
        for error in result.errors:
            message = error.get("message", "").lower()
            
            # Terminal errors
            terminal_patterns = [
                "404",
                "403",
                "access denied",
                "blocked",
                "forbidden",
                "not found",
                "page not found",
                "account suspended",
                "page requires",
            ]
            
            for pattern in terminal_patterns:
                if pattern in message:
                    error["severity"] = ErrorSeverity.TERMINAL.value
                    break
            
            # Transient errors
            transient_patterns = [
                "timeout",
                "connection refused",
                "tunnel",
                "proxy error",
                "503",
                "502",
                "500",
                "bad gateway",
                "service unavailable",
                "temporary",
            ]
            
            if error.get("severity") == ErrorSeverity.UNKNOWN.value:
                for pattern in transient_patterns:
                    if pattern in message:
                        error["severity"] = ErrorSeverity.TRANSIENT.value
                        break
    
    async def cleanup(self) -> None:
        """Clean up resources."""
        # Browser pool cleanup is handled separately
        pass
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} site={self.site_name} worker={self.worker_id}>"
