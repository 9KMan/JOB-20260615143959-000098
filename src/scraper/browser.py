# src/scraper/browser.py
"""Playwright browser pool and context management with stealth features."""

import asyncio
import hashlib
import json
import os
import shutil
import signal
import sys
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import UUID, uuid4

import yaml
from playwright.async_api import (
    Browser,
    BrowserContext,
    BrowserType,
    ChromiumBrowser,
    Page,
    Playwright,
    ProxySettings,
    async_playwright,
)
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config.settings import get_settings
from src.utils.logging import get_logger

logger = get_logger(__name__)

# stealth plugin path handling
STEALTH_PLUGIN_PATH = os.environ.get(
    "STEALTH_PLUGIN_PATH",
    str(Path(__file__).parent.parent.parent / "node_modules" / "puppeteer-extra-plugin-stealth")
)


@dataclass
class BrowserProfile:
    """Browser profile configuration for context creation."""
    
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    viewport_width: int = 1920
    viewport_height: int = 1080
    device_scale_factor: float = 1.0
    is_mobile: bool = False
    has_touch: bool = False
    locale: str = "en-US"
    timezone_id: str = "America/New_York"
    permissions: List[str] = field(default_factory=lambda: ["geolocation"])
    color_scheme: str = "light"
    java_script_enabled: bool = True
    bypass_csp: bool = False
    extra_http_headers: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert profile to dictionary for Playwright."""
        return {
            "user_agent": self.user_agent,
            "viewport": {
                "width": self.viewport_width,
                "height": self.viewport_height,
                "device_scale_factor": self.device_scale_factor,
            },
            "screen": {
                "width": self.viewport_width,
                "height": self.viewport_height,
            },
            "is_mobile": self.is_mobile,
            "has_touch": self.has_touch,
            "locale": self.locale,
            "timezone_id": self.timezone_id,
            "permissions": self.permissions,
            "color_scheme": self.color_scheme,
            "java_script_enabled": self.java_script_enabled,
            "bypass_csp": self.bypass_csp,
            "extra_http_headers": self.extra_http_headers,
        }


@dataclass
class BrowserContext:
    """Wrapper for browser context with proxy and profile support."""
    
    context_id: UUID
    context: BrowserContext
    profile: BrowserProfile
    proxy: Optional[Dict[str, str]] = None
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    request_count: int = 0
    error_count: int = 0
    
    def touch(self) -> None:
        """Update last used timestamp."""
        self.last_used = time.time()
    
    def increment_requests(self) -> None:
        """Increment request counter."""
        self.request_count += 1
        self.touch()
    
    def increment_errors(self) -> None:
        """Increment error counter."""
        self.error_count += 1
        self.touch()
    
    @property
    def age_seconds(self) -> float:
        """Get age of context in seconds."""
        return time.time() - self.created_at
    
    @property
    def error_rate(self) -> float:
        """Calculate error rate."""
        if self.request_count == 0:
            return 0.0
        return self.error_count / self.request_count


class BrowserPool:
    """Manages a pool of Playwright browser instances per worker.
    
    Features:
    - Per-worker browser instances to avoid Xvfb lock contention
    - Contexts created per job with fresh profiles
    - Automatic cleanup of stale contexts
    - Proxy support with session binding
    """
    
    def __init__(
        self,
        max_browsers: int = 2,
        max_contexts_per_browser: int = 5,
        context_ttl_seconds: int = 300,
        max_context_age_seconds: int = 600,
        enable_stealth: bool = True,
        headless: Optional[bool] = None,
    ):
        """Initialize browser pool.
        
        Args:
            max_browsers: Maximum browser instances to maintain
            max_contexts_per_browser: Max contexts per browser instance
            context_ttl_seconds: Context time-to-live for reuse
            max_context_age_seconds: Force recreate context after this age
            enable_stealth: Enable stealth mode (navigator.webdriver = false)
            headless: Override headless mode (None = auto based on DISPLAY)
        """
        self.settings = get_settings()
        self.max_browsers = max_browsers
        self.max_contexts_per_browser = max_contexts_per_browser
        self.context_ttl_seconds = context_ttl_seconds
        self.max_context_age_seconds = max_context_age_seconds
        self.enable_stealth = enable_stealth
        self.headless = headless
        
        self._playwright: Optional[Playwright] = None
        self._browsers: Dict[str, Browser] = {}
        self._browser_profiles: Dict[str, BrowserProfile] = {}
        self._contexts: Dict[UUID, BrowserContext] = {}
        self._context_semaphore: Optional[asyncio.Semaphore] = None
        self._lock = asyncio.Lock()
        self._initialized = False
        
        # Set up signal handlers for graceful shutdown
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, self._signal_handler)
            except (ValueError, OSError):
                pass  # Not in main thread
    
    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown")
        asyncio.create_task(self.cleanup())
    
    async def initialize(self) -> None:
        """Initialize Playwright and start browser instances."""
        if self._initialized:
            return
        
        async with self._lock:
            if self._initialized:
                return
            
            logger.info("Initializing Playwright browser pool")
            
            # Determine headless mode
            display = os.environ.get("DISPLAY", "")
            is_headless = self.headless if self.headless is not None else not display
            
            if is_headless:
                logger.info("Running in headless mode (no DISPLAY)")
            else:
                logger.info(f"Running with DISPLAY={display}")
            
            # Launch Playwright
            self._playwright = await async_playwright().start()
            
            # Determine browser executable
            chromium_executable = self._find_chromium_executable()
            logger.info(f"Using Chromium: {chromium_executable}")
            
            # Start initial browsers
            for i in range(self.max_browsers):
                browser_id = f"browser-{i}-{uuid4().hex[:8]}"
                await self._start_browser(browser_id, chromium_executable, is_headless)
            
            self._context_semaphore = asyncio.Semaphore(
                self.max_browsers * self.max_contexts_per_browser
            )
            
            self._initialized = True
            logger.info(f"Browser pool initialized with {len(self._browsers)} browsers")
    
    def _find_chromium_executable(self) -> Optional[str]:
        """Find Chromium executable path."""
        possible_paths = [
            shutil.which("chromium"),
            shutil.which("chromium-browser"),
            shutil.which("google-chrome"),
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/usr/bin/google-chrome",
            "/ms-playwright/chromium-1097/chrome-linux/chrome",
            "/ms-playwright/chromium-1169/chrome-linux/chrome",
        ]
        
        for path in possible_paths:
            if path and os.path.exists(path):
                return path
        
        return None  # Let Playwright download its own
    
    async def _start_browser(
        self,
        browser_id: str,
        executable_path: Optional[str] = None,
        headless: bool = True,
    ) -> Browser:
        """Start a browser instance.
        
        Args:
            browser_id: Unique identifier for this browser
            executable_path: Path to Chromium executable
            headless: Whether to run headless
            
        Returns:
            Started browser instance
        """
        launch_options = {
            "headless": headless,
            "args": self._get_browser_args(),
        }
        
        if executable_path:
            launch_options["executable_path"] = executable_path
        
        browser = await self._playwright.chromium.launch(**launch_options)
        self._browsers[browser_id] = browser
        
        # Create default profile
        self._browser_profiles[browser_id] = BrowserProfile()
        
        logger.info(f"Started browser {browser_id} (headless={headless})")
        return browser
    
    def _get_browser_args(self) -> List[str]:
        """Get Chromium launch arguments for stealth and stability."""
        return [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-site-isolation-trials",
            "--disable-infobars",
            "--disable-notifications",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-default-apps",
            "--disable-sync",
            "--disable-translate",
            "--metrics-recording-only",
            "--mute-audio",
            "--no-first-run",
            "--no-zygote",
            "--safebrowsing-disable-auto-update",
            "--ignore-certificate-errors",
            "--ignore-ssl-errors",
            "--ignore-certificate-errors-spki-list",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-window-activation",
            "--disable-focus-on-load",
            "--no-crash-upload",
            "--disable-hang-monitor",
            "--disable-prompt-on-repost",
            "--disable-client-side-phishing-detection",
            "--disable-crash-reporter",
            "--disable-oopr-debug-crash-dump",
            "--no-crashpad",
            "--disable-logging",
            "--disable-login-animations",
            "--disable-low-res-tiling",
            "--log-level=3",
            "--disable-flash-animations",
            "--enable-features=NetworkService,NetworkServiceInProcess",
            "--window-size=1920,1080",
            "--start-maximized",
        ]
    
    @asynccontextmanager
    async def acquire_context(
        self,
        profile: Optional[BrowserProfile] = None,
        proxy: Optional[Dict[str, str]] = None,
        timeout_seconds: float = 30.0,
    ) -> AsyncGenerator[BrowserContext, None]:
        """Acquire a browser context from the pool.
        
        Args:
            profile: Browser profile to use
            proxy: Proxy configuration (server, username, password)
            timeout_seconds: Timeout for context acquisition
            
        Yields:
            BrowserContext wrapper
            
        Raises:
            TimeoutError: If context cannot be acquired within timeout
        """
        if not self._initialized:
            await self.initialize()
        
        await self._context_semaphore.acquire()
        
        context_wrapper: Optional[BrowserContext] = None
        
        try:
            # Try to reuse an existing context
            context_wrapper = await self._find_reusable_context(profile, proxy)
            
            if context_wrapper is None:
                # Create new context
                context_wrapper = await self._create_context(profile, proxy)
            
            logger.debug(
                f"Acquired context {context_wrapper.context_id} "
                f"(errors={context_wrapper.error_count})"
            )
            
            yield context_wrapper
            
        except Exception as e:
            if context_wrapper:
                context_wrapper.increment_errors()
            raise
        finally:
            if self._context_semaphore.locked():
                self._context_semaphore.release()
    
    async def _find_reusable_context(
        self,
        profile: Optional[BrowserProfile],
        proxy: Optional[Dict[str, str]],
    ) -> Optional[BrowserContext]:
        """Find an existing context suitable for reuse."""
        now = time.time()
        
        for context_id, wrapper in list(self._contexts.items()):
            # Check if context is still valid
            age = now - wrapper.last_used
            
            if age > self.context_ttl_seconds:
                # Context too old, remove it
                await self._close_context(wrapper)
                continue
            
            if wrapper.age_seconds > self.max_context_age_seconds:
                # Context too old overall, recreate
                await self._close_context(wrapper)
                continue
            
            # Check if context meets requirements
            if profile and wrapper.profile != profile:
                continue
            
            if proxy and wrapper.proxy != proxy:
                continue
            
            # Check error rate
            if wrapper.error_rate > 0.3:  # 30% error rate threshold
                await self._close_context(wrapper)
                continue
            
            # Context is reusable
            wrapper.touch()
            return wrapper
        
        return None
    
    async def _create_context(
        self,
        profile: Optional[BrowserProfile],
        proxy: Optional[Dict[str, str]],
    ) -> BrowserContext:
        """Create a new browser context."""
        # Select browser with fewest contexts
        browser_id = min(
            self._browsers.keys(),
            key=lambda bid: sum(
                1 for c in self._contexts.values()
                if c.context.browser and str(c.context.browser) == str(self._browsers.get(bid))
            )
        )
        browser = self._browsers[browser_id]
        
        # Use provided profile or browser default
        context_profile = profile or self._browser_profiles.get(browser_id, BrowserProfile())
        
        # Build context options
        context_options = context_profile.to_dict()
        
        if proxy:
            context_options["proxy"] = {
                "server": proxy["server"],
            }
            if "username" in proxy and "password" in proxy:
                context_options["proxy"]["username"] = proxy["username"]
                context_options["proxy"]["password"] = proxy["password"]
        
        # Create context with storage state if needed
        context_id = uuid4()
        
        try:
            context = await browser.new_context(**context_options)
        except Exception as e:
            logger.error(f"Failed to create context: {e}")
            raise
        
        wrapper = BrowserContext(
            context_id=context_id,
            context=context,
            profile=context_profile,
            proxy=proxy,
        )
        
        self._contexts[context_id] = wrapper
        
        # Apply stealth modifications
        if self.enable_stealth:
            await self._apply_stealth(context)
        
        logger.debug(f"Created new context {context_id}")
        return wrapper
    
    async def _apply_stealth(self, context: BrowserContext) -> None:
        """Apply stealth modifications to context.
        
        This modifies navigator properties to avoid detection.
        """
        # Clear webdriver flag
        await context.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
                configurable: true
            });
        """)
        
        # Mock permissions API
        await context.context.add_init_script("""
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
        """)
        
        # Remove automation extensions
        await context.context.add_init_script("""
            window.chrome = { runtime: {} };
        """)
        
        # Mock plugins
        await context.context.add_init_script("""
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    {
                        name: 'Chrome PDF Plugin',
                        description: 'Portable Document Format',
                        filename: 'internal-pdf-viewer'
                    },
                    {
                        name: 'Chrome PDF Viewer',
                        description: '',
                        filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'
                    },
                    {
                        name: 'Native Client',
                        description: '',
                        filename: 'internal-nacl-plugin'
                    }
                ],
                configurable: true
            });
        """)
        
        # Mock languages
        await context.context.add_init_script("""
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en', 'en-GB'],
                configurable: true
            });
        """)
    
    async def _close_context(self, wrapper: BrowserContext) -> None:
        """Close and remove a context."""
        try:
            await wrapper.context.close()
        except Exception as e:
            logger.warning(f"Error closing context {wrapper.context_id}: {e}")
        
        self._contexts.pop(wrapper.context_id, None)
    
    async def cleanup(self) -> None:
        """Clean up all browsers and contexts."""
        logger.info("Cleaning up browser pool")
        
        async with self._lock:
            # Close all contexts
            for wrapper in list(self._contexts.values()):
                try:
                    await wrapper.context.close()
                except Exception as e:
                    logger.warning(f"Error closing context: {e}")
            
            self._contexts.clear()
            
            # Close all browsers
            for browser_id, browser in list(self._browsers.items()):
                try:
                    await browser.close()
                except Exception as e:
                    logger.warning(f"Error closing browser {browser_id}: {e}")
            
            self._browsers.clear()
            
            # Stop Playwright
            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception as e:
                    logger.warning(f"Error stopping Playwright: {e}")
                self._playwright = None
            
            self._initialized = False
            logger.info("Browser pool cleaned up")
    
    @property
    def stats(self) -> Dict[str, Any]:
        """Get pool statistics."""
        return {
            "initialized": self._initialized,
            "browsers": len(self._browsers),
            "contexts": len(self._contexts),
            "contexts_by_age": {
                str(cid): {
                    "age_seconds": ctx.age_seconds,
                    "error_rate": ctx.error_rate,
                    "request_count": ctx.request_count,
                }
                for cid, ctx in self._contexts.items()
            },
        }
