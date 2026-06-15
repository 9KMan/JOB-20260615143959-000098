# src/workers/scraper_worker.py
"""
Scraper worker with Playwright browser management and anti-bot mitigation.
"""
import asyncio
import json
import logging
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

import pyppeteer
from pyppeteer import launch
from pyppeteer.browser import Browser
from pyppeteer.page import Page
from pyppeteer.errors import TimeoutError as PyppeteerTimeout

from src.config import config
from src.models import ScrapeJob, ErrorLog, ProxyError, get_session_factory
from src.workers.base_worker import BaseWorker, JobResult
from src.services.llm_classifier import LLMErrorClassifier

logger = logging.getLogger(__name__)


class XvfbManager:
    """
    Manages Xvfb (virtual framebuffer) for headless Chrome.
    Handles display allocation and cleanup to prevent infra races.
    """
    
    def __init__(self, display_number: Optional[int] = None):
        self.display_number = display_number or self._find_available_display()
        self.process: Optional[subprocess.Popen] = None
        self.lock_file: Optional[Path] = None
    
    def _find_available_display(self) -> int:
        """Find an available display number."""
        base = int(os.getenv("XVFB_BASE_DISPLAY", "99"))
        max_displays = int(os.getenv("XVFB_MAX_DISPLAYS", "10"))
        
        for i in range(base, base + max_displays):
            lock_file = Path(f"/tmp/.X{i}-lock")
            if not lock_file.exists():
                return i
        
        raise RuntimeError("No available Xvfb displays")
    
    def start(self) -> str:
        """Start Xvfb and return display string."""
        display = f":{self.display_number}"
        
        # Clean up stale lock file if present
        lock_file = Path(f"/tmp/.X{self.display_number}-lock")
        if lock_file.exists():
            try:
                # Check if the process is actually running
                pid = int(lock_file.read_text().strip())
                try:
                    os.kill(pid, 0)
                    logger.warning(f"Stale lock file but process {pid} is alive")
                except ProcessLookupError:
                    logger.info(f"Removing stale lock file for display {self.display_number}")
                    lock_file.unlink()
            except (ValueError, FileNotFoundError):
                lock_file.unlink()
        
        # Start Xvfb
        cmd = [
            "Xvfb",
            display,
            "-screen", "0",
            f"{config.browser.viewport_width}x{config.browser.viewport_height}x24",
            "-ac",
            "+extension", "GLX",
            "+render",
            "-noreset"
        ]
        
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid
        )
        
        # Wait for startup
        time.sleep(0.5)
        
        if self.process.poll() is not None:
            raise RuntimeError("Xvfb failed to start")
        
        self.lock_file = lock_file
        return display
    
    def stop(self):
        """Stop Xvfb and clean up."""
        if self.process:
            try:
                os.killpg(os.getpgid(self.process.pid), 9)
            except ProcessLookupError:
                pass
            self.process = None
        
        if self.lock_file and self.lock_file.exists():
            try:
                self.lock_file.unlink()
            except FileNotFoundError:
                pass
    
    def __enter__(self):
        return self.start()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


class BrowserManager:
    """
    Manages Playwright/Chromium browser instances with stealth settings.
    Handles anti-bot mitigation and slow render timeouts.
    """
    
    def __init__(self, proxy_url: Optional[str] = None, exit_node: Optional[int] = None):
        self.proxy_url = proxy_url
        self.exit_node = exit_node
        self.browser: Optional[Browser] = None
        self._page: Optional[Page] = None
        self._screenshot_dir = Path(os.getenv("SCREENSHOT_DIR", "/tmp/screenshots"))
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)
    
    async def launch(self) -> Browser:
        """Launch browser with stealth configuration."""
        from pyppeteer.launcher import launch as pyppeteer_launch
        
        # Build Chrome arguments for stealth mode
        args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-accelerated-2d-canvas",
            "--disable-gpu",
            "--window-size={},{}".format(config.browser.viewport_width, config.browser.viewport_height),
            "--disable-web-security" if config.browser.disable_web_security else "",
            "--disable-features=IsolateOrigins,site-per-process",
        ]
        
        # Proxy configuration
        if self.proxy_url:
            args.append(f"--proxy-server={self.proxy_url}")
        
        # Stealth mode modifications
        if config.browser.stealth_mode:
            args.extend([
                "--disable-blink-features=AutomationControlled",
                "--exclude-switches", "enable-automation",
                "--enable-features=NetworkService,NetworkServiceInProcess",
            ])
        
        # Filter empty strings
        args = [arg for arg in args if arg]
        
        self.browser = await pyppeteer_launch(
            headless=config.browser.headless,
            args=args,
            dumpio=False,
            autoClose=False,
        )
        
        # Apply stealth modifications
        if config.browser.stealth_mode:
            await self._apply_stealth_modifications()
        
        return self.browser
    
    async def _apply_stealth_modifications(self):
        """Apply JavaScript modifications to avoid detection."""
        if not self.browser:
            return
        
        for page in self.browser.pages:
            await page.evaluateOnNewDocument("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
                
                window.chrome = {
                    runtime: {}
                };
                
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
            """)
    
    async def new_page(self) -> Page:
        """Create a new page with default settings."""
        if not self.browser:
            await self.launch()
        
        page = await self.browser.newPage()
        
        # Set viewport
        await page.setViewport({
            "width": config.browser.viewport_width,
            "height": config.browser.viewport_height,
        })
        
        # Set user agent
        await page.setUserAgent(config.browser.user_agent)
        
        # Set default timeout
        page.setDefaultTimeout(config.browser.navigation_timeout_ms)
        page.setDefaultNavigationTimeout(config.browser.navigation_timeout_ms)
        
        return page
    
    async def navigate_and_scrape(
        self,
        url: str,
        page: Optional[Page] = None,
        selectors: Optional[Dict[str, str]] = None
    ) -> Tuple[Optional[Page], str, Optional[str]]:
        """
        Navigate to URL and scrape content.
        
        Returns:
            Tuple of (page, html_content, error_message)
        """
        should_close_page = page is None
        page = page or await self.new_page()
        
        try:
            # Navigate with extended timeout for slow pages
            response = await page.goto(
                url,
                {
                    "waitUntil": "networkidle2",
                    "timeout": config.browser.navigation_timeout_ms,
                }
            )
            
            # Check for anti-bot responses
            status = response.status if response else None
            
            # Handle cookie banners
            if config.browser.accept_cookies:
                await self._handle_cookie_banner(page)
            
            # Wait for page to stabilize
            await asyncio.sleep(1)  # Allow dynamic content to load
            
            # Get page content
            html = await page.content()
            
            # Check for captcha
            if self._detect_captcha(page):
                return page, "", "CAPTCHA_DETECTED"
            
            return page, html, None
            
        except PyppeteerTimeout as e:
            logger.warning(f"Navigation timeout for {url}: {e}")
            # Try to get partial content
            try:
                html = await page.content()
                return page, html, "PARTIAL_CONTENT_TIMEOUT"
            except Exception:
                return page, "", f"TIMEOUT: {str(e)}"
                
        except Exception as e:
            logger.error(f"Navigation error for {url}: {e}")
            return page, "", f"NAVIGATION_ERROR: {str(e)}"
        
        finally:
            if should_close_page and page:
                await page.close()
    
    async def _handle_cookie_banner(self, page: Page):
        """Attempt to dismiss cookie banners."""
        try:
            # Try common cookie banner selectors
            selectors = config.browser.cookie_banner_selector.split(",")
            
            for selector in selectors:
                selector = selector.strip()
                try:
                    button = await page.querySelector(selector)
                    if button:
                        await button.click()
                        logger.debug(f"Dismissed cookie banner: {selector}")
                        await asyncio.sleep(0.5)
                        return
                except Exception:
                    continue
                    
        except Exception as e:
            logger.debug(f"Could not handle cookie banner: {e}")
    
    def _detect_captcha(self, page: Page) -> bool:
        """Detect common CAPTCHA patterns."""
        # Check page title
        title = page.url or ""
        captcha_patterns = [
            "captcha", "recaptcha", "hcaptcha", "arkose",
            "access denied", "blocked", "forbidden"
        ]
        
        for pattern in captcha_patterns:
            if pattern.lower() in title.lower():
                return True
        
        return False
    
    async def take_screenshot(self, page: Page, job_id: str) -> Optional[str]:
        """Take screenshot of current page state."""
        if not config.browser.skip_captcha_screenshots:
            return None
        
        try:
            filename = f"{job_id}_{int(time.time())}.png"
            filepath = self._screenshot_dir / filename
            await page.screenshot({"path": str(filepath), "fullPage": True})
            return str(filepath)
        except Exception as e:
            logger.warning(f"Failed to take screenshot: {e}")
            return None
    
    async def close(self):
        """Close browser and clean up."""
        if self.browser:
            try:
                await self.browser.close()
            except Exception as e:
                logger.warning(f"Error closing browser: {e}")
            self.browser = None


class ScrapeWorker(BaseWorker):
    """
    Worker that processes scraping jobs using Playwright.
    
    Handles:
    - Browser lifecycle management
    - Proxy rotation with sticky sessions
    - Anti-bot mitigation
    - Error classification via LLM
    - Database persistence
    """
    
    def __init__(self, worker_id: Optional[str] = None):
        super().__init__(worker_id)
        
        # Browser manager
        self._browser_manager: Optional[BrowserManager] = None
        self._xvfb: Optional[XvfbManager] = None
        
        # LLM classifier for error categorization
        self._llm_classifier = LLMErrorClassifier()
        
        # Track exit node assignment
        self._current_exit_node: Optional[int] = None
        self._exit_node_lock = asyncio.Lock()
    
    async def _get_exit_node(self) -> int:
        """Get next available exit node, respecting circuit breakers."""
        max_nodes = config.proxy.exit_node_count
        
        # Try each exit node
        for i in range(max_nodes):
            exit_node = (self._current_exit_node or 0) + i + 1
            exit_node = exit_node % max_nodes
            
            cb = self._get_proxy_circuit_breaker(exit_node)
            if cb.is_available():
                self._current_exit_node = exit_node
                return exit_node
        
        # All circuits open, wait and try again
        await asyncio.sleep(config.rabbitmq.circuit_breaker_timeout)
        return await self._get_exit_node()
    
    async def _setup_browser(self, exit_node: Optional[int] = None) -> BrowserManager:
        """Set up browser with proxy configuration."""
        # Start Xvfb if needed
        if not config.browser.headless:
            self._xvfb = XvfbManager()
            os.environ["DISPLAY"] = self._xvfb.start()
        elif os.getenv("DISPLAY"):
            os.environ["DISPLAY"] = os.getenv("DISPLAY")
        else:
            # Use Xvfb even for headless to avoid display issues
            self._xvfb = XvfbManager()
            os.environ["DISPLAY"] = self._xvfb.start()
        
        # Get proxy URL
        proxy_url = config.proxy.get_proxy_url(exit_node)
        
        # Create browser manager
        self._browser_manager = BrowserManager(
            proxy_url=proxy_url,
            exit_node=exit_node
        )
        
        return self._browser_manager
    
    async def _cleanup_browser(self):
        """Clean up browser resources."""
        if self._browser_manager:
            await self._browser_manager.close()
            self._browser_manager = None
        
        if self._xvfb:
            self._xvfb.stop()
            self._xvfb = None
        
        if "DISPLAY" in os.environ:
            del os.environ["DISPLAY"]
    
    def _parse_message(self, body: bytes) -> Dict[str, Any]:
        """Parse message body into job data."""
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message: {e}")
            return {"job_id": "unknown", "raw_body": body.decode("utf-8", errors="replace")}
    
    def _process_job(self, message: Dict[str, Any]) -> JobResult:
        """Process a scraping job (synchronous wrapper)."""
        # Run async processing in event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self._process_job_async(message))
        finally:
            loop.close()
    
    async def _process_job_async(self, message: Dict[str, Any]) -> JobResult:
        """Process a scraping job asynchronously."""
        job_id = message.get("job_id")
        url = message.get("url")
        target_fields = message.get("target_fields", [])
        site = message.get("site", self._extract_site_from_url(url))
        
        db_session = self._session_factory()
        start_time = datetime.now(timezone.utc)
        
        try:
            # Update job status
            job = db_session.query(ScrapeJob).filter(ScrapeJob.id == job_id).first()
            if job:
                job.status = "in_progress"
                job.started_at = start_time
                job.assigned_worker_id = self.worker_id
                db_session.commit()
            
            # Get exit node for this attempt
            exit_node = await self._get_exit_node()
            
            # Check circuit breaker
            cb = self._get_proxy_circuit_breaker(exit_node)
            if not cb.is_available():
                logger.warning(f"Exit node {exit_node} circuit is open, retrying later")
                return JobResult(
                    success=False,
                    error_message=f"Exit node {exit_node} temporarily unavailable",
                    error_category="proxy",
                    is_permanent=False,
                    exit_node=exit_node,
                )
            
            # Set up browser
            browser_manager = await self._setup_browser(exit_node)
            
            try:
                # Navigate and scrape
                page, html, error = await browser_manager.navigate_and_scrape(url)
                
                if error:
                    # Classify the error
                    error_result = await self._classify_error(error, url, site, exit_node)
                    
                    # Record proxy error if applicable
                    if "TUNNEL" in error or "PROXY" in error:
                        self._record_proxy_error(db_session, job_id, error, exit_node)
                    
                    # Take screenshot for debugging
                    screenshot_path = await browser_manager.take_screenshot(page, job_id) if page else None
                    
                    # Record error log
                    self._record_error_log(
                        db_session, job_id, error, error_result.category, 
                        screenshot_path, exit_node, retry_count=message.get("retry_count", 0)
                    )
                    
                    # Update circuit breaker
                    if error_result.category == "proxy":
                        cb.record_failure(error)
                    
                    return JobResult(
                        success=False,
                        error_message=error,
                        error_code=error_result.error_code,
                        error_category=error_result.category,
                        is_permanent=error_result.is_permanent,
                        exit_node=exit_node,
                    )
                
                # Extract data from HTML
                extracted_data = await self._extract_data(html, target_fields)
                
                # Calculate duration
                duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
                
                # Update job with results
                if job:
                    job.status = "completed"
                    job.completed_at = datetime.now(timezone.utc)
                    job.total_duration_ms = duration_ms
                    job.scraped_data = extracted_data
                    job.raw_html_length = len(html)
                    job.proxy_exit_node = exit_node
                    job.extraction_confidence = "high"
                    db_session.commit()
                
                # Record success
                cb.record_success()
                
                return JobResult(
                    success=True,
                    data=extracted_data,
                    exit_node=exit_node,
                )
                
            finally:
                await self._cleanup_browser()
                
        except Exception as e:
            logger.exception(f"Error processing job {job_id}: {e}")
            
            # Classify error
            error_result = await self._classify_error(str(e), url, site, self._current_exit_node)
            
            # Update job as failed
            job = db_session.query(ScrapeJob).filter(ScrapeJob.id == job_id).first()
            if job:
                job.status = "failed"
                job.error_message = str(e)
                job.error_category = error_result.category
                job.is_permanent_failure = error_result.is_permanent
                db_session.commit()
            
            return JobResult(
                success=False,
                error_message=str(e),
                error_category=error_result.category,
                is_permanent=error_result.is_permanent,
            )
            
        finally:
            db_session.close()
    
    async def _classify_error(
        self, 
        error: str, 
        url: str, 
        site: str,
        exit_node: Optional[int]
    ) -> "ErrorClassification":
        """Classify error using LLM or heuristics."""
        # Use heuristic classification for common errors
        error_lower = error.lower()
        
        # Proxy-specific errors
        if any(x in error_lower for x in ["tunnel", "err_tunnel", "proxy error", "connection refused"]):
            return ErrorClassification(
                category="proxy",
                error_code="PROXY_ERROR",
                is_permanent=False,
                reasoning="Proxy connection error, may recover with retry"
            )
        
        # Anti-bot detection
        if any(x in error_lower for x in ["captcha", "blocked", "access denied", "forbidden", "403", "429"]):
            return ErrorClassification(
                category="anti_bot",
                error_code="ANTI_BOT_DETECTED",
                is_permanent=False,
                reasoning="Anti-bot detection, may need stealth improvements"
            )
        
        # Terminal errors
        if any(x in error_lower for x in ["certificate", "ssl", "dns", "not found", "404"]):
            return ErrorClassification(
                category="terminal",
                error_code="TERMINAL_ERROR",
                is_permanent=True,
                reasoning="Terminal error, no point retrying"
            )
        
        # Timeout errors
        if "timeout" in error_lower:
            return ErrorClassification(
                category="transient",
                error_code="TIMEOUT",
                is_permanent=False,
                reasoning="Timeout error, may recover with retry"
            )
        
        # Use LLM for classification if available
        if self._llm_classifier.is_available():
            try:
                return await self._llm_classifier.classify_error(error, url, site)
            except Exception as e:
                logger.warning(f"LLM classification failed: {e}")
        
        # Default to transient
        return ErrorClassification(
            category="unknown",
            error_code="UNKNOWN",
            is_permanent=False,
            reasoning="Unknown error, treating as transient"
        )
    
    def _extract_site_from_url(self, url: str) -> str:
        """Extract site name from URL."""
        try:
            from urllib.parse import urlparse
            return urlparse(url).netloc
        except Exception:
            return "unknown"
    
    async def _extract_data(
        self, 
        html: str, 
        target_fields: List[str]
    ) -> Dict[str, Any]:
        """Extract structured data from HTML."""
        # Simple extraction for now - can be enhanced with BeautifulSoup or LLM
        extracted = {}
        
        # This would be replaced with actual extraction logic
        # based on the target site's structure
        for field in target_fields:
            extracted[field] = None
        
        return extracted
    
    def _record_error_log(
        self,
        db_session,
        job_id: str,
        error_message: str,
        error_category: str,
        screenshot_path: Optional[str],
        exit_node: Optional[int],
        retry_count: int
    ):
        """Record detailed error log for debugging."""
        try:
            error_log = ErrorLog(
                job_id=job_id,
                error_message=error_message,
                error_category=error_category,
                screenshot_path=screenshot_path,
                proxy_exit_node=exit_node,
                retry_number=retry_count,
            )
            db_session.add(error_log)
            db_session.commit()
        except Exception as e:
            logger.error(f"Failed to record error log: {e}")
    
    def _record_proxy_error(
        self,
        db_session,
        job_id: str,
        error_message: str,
        exit_node: Optional[int]
    ):
        """Record proxy-specific error for pattern detection."""
        try:
            proxy_error = ProxyError(
                job_id=job_id,
                error_code="ERR_TUNNEL" if "TUNNEL" in error_message else "PROXY_ERROR",
                error_message=error_message,
                exit_node=exit_node,
            )
            db_session.add(proxy_error)
            db_session.commit()
        except Exception as e:
            logger.error(f"Failed to record proxy error: {e}")


@dataclass
class ErrorClassification:
    """Result of error classification."""
    category: str  # transient, terminal, proxy, anti_bot, infra, unknown
    error_code: str
    is_permanent: bool
    reasoning: str


def run_worker():
    """Entry point for worker process."""
    import logging
    from src.config.settings import configure_logging, validate_all
    
    configure_logging()
    
    # Validate configuration
    result = validate_all()
    if not result.valid:
        logger.error("Configuration validation failed")
        sys.exit(1)
    
    # Initialize database
    init_db()
    
    # Run worker
    worker = ScrapeWorker()
    worker.start_consuming()


if __name__ == "__main__":
    run_worker()
