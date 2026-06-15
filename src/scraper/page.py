# src/scraper/page.py
"""Page interaction helpers including stealth, captcha handling, and cookies."""

import asyncio
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from playwright.async_api import Page, Response, TimeoutError as PlaywrightTimeout
from tenacity import retry, stop_after_attempt, wait_exponential

from src.utils.logging import get_logger

logger = get_logger(__name__)


class CookieConsentType(Enum):
    """Types of cookie consent banners."""
    NONE = "none"
    SIMPLE_ACCEPT = "simple_accept"  # Single "Accept" button
    DETAILED = "detailed"  # Multiple options
    GDPR = "gdpr"  # EU-style with reject option
    CCPA = "ccpa"  # California-style "Do Not Sell"


@dataclass
class PageInteractionResult:
    """Result of a page interaction."""
    success: bool
    error: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    cookies_accepted: bool = False
    captcha_solved: bool = False
    captcha_type: Optional[str] = None
    navigation_completed: bool = False
    response_status: Optional[int] = None
    final_url: Optional[str] = None


@dataclass
class CookieConsentConfig:
    """Configuration for cookie consent handling."""
    accept_button_selectors: List[str] = field(default_factory=lambda: [
        "#onetrust-accept-btn-handler",
        "#cookie-accept",
        ".cookie-accept",
        "[data-testid='cookie-accept']",
        "button[class*='accept']",
        "button:has-text('Accept')",
        "button:has-text('I agree')",
        "button:has-text('Got it')",
        "[aria-label*='Accept']",
        "[aria-label*='agree']",
    ])
    reject_button_selectors: List[str] = field(default_factory=lambda: [
        "[aria-label*='Reject']",
        "[aria-label*='Decline']",
        ".reject-cookies",
    ])
    settings_button_selectors: List[str] = field(default_factory=lambda: [
        "[aria-label*='Cookie Settings']",
        "[aria-label*='privacy']",
        "a:has-text('Cookie Settings')",
    ])
    modal_selectors: List[str] = field(default_factory=lambda: [
        "#onetrust-consent-sdk",
        ".cookie-consent",
        ".cookie-banner",
        "[role='dialog']",
        ".cc-banner",
    ])
    wait_timeout_ms: int = 5000
    dismiss_delay_ms: int = 1000


@dataclass
class CaptchaConfig:
    """Configuration for captcha detection and handling."""
    detection_selectors: List[str] = field(default_factory=lambda: [
        '[data-sitekey]',
        '.g-recaptcha',
        '#captcha',
        '.captcha-container',
        '[class*="captcha"]',
        'iframe[src*="recaptcha"]',
        'iframe[src*="hcaptcha"]',
        'iframe[src*="friendly-captcha"]',
    ])
    detection_timeout_ms: int = 3000
    max_retries: int = 3
    retry_delay_ms: int = 2000


class PageHelper:
    """Helper class for page interactions with stealth and automation features."""
    
    def __init__(
        self,
        page: Page,
        cookie_config: Optional[CookieConsentConfig] = None,
        captcha_config: Optional[CaptchaConfig] = None,
    ):
        """Initialize page helper.
        
        Args:
            page: Playwright page instance
            cookie_config: Cookie consent handling configuration
            captcha_config: Captcha detection configuration
        """
        self.page = page
        self.cookie_config = cookie_config or CookieConsentConfig()
        self.captcha_config = captcha_config or CaptchaConfig()
        self._response_count = 0
        self._error_count = 0
    
    async def navigate_with_retry(
        self,
        url: str,
        timeout_ms: int = 30000,
        wait_until: str = "domcontentloaded",
        max_retries: int = 3,
    ) -> PageInteractionResult:
        """Navigate to URL with automatic retry on certain errors.
        
        Args:
            url: Target URL
            timeout_ms: Navigation timeout
            wait_until: When to consider navigation complete
            max_retries: Maximum retry attempts
            
        Returns:
            Interaction result
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                self._response_count += 1
                
                response = await self.page.goto(
                    url,
                    timeout=timeout_ms,
                    wait_until=wait_until,
                )
                
                status = response.status if response else None
                final_url = self.page.url
                
                logger.debug(
                    f"Navigated to {url} "
                    f"(status={status}, attempt={attempt + 1})"
                )
                
                return PageInteractionResult(
                    success=True,
                    navigation_completed=True,
                    response_status=status,
                    final_url=final_url,
                )
                
            except PlaywrightTimeout as e:
                last_error = f"Navigation timeout: {e}"
                logger.warning(
                    f"Navigation timeout to {url} "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                
            except Exception as e:
                last_error = str(e)
                self._error_count += 1
                logger.warning(
                    f"Navigation error to {url}: {e} "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
            
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
        return PageInteractionResult(
            success=False,
            error=last_error,
            navigation_completed=False,
        )
    
    async def wait_for_render(
        self,
        min_delay_ms: int = 500,
        max_delay_ms: int = 3000,
        selector: Optional[str] = None,
    ) -> bool:
        """Wait for page to fully render.
        
        Args:
            min_delay_ms: Minimum wait time
            max_delay_ms: Maximum initial wait time
            selector: Optional selector to wait for
            
        Returns:
            True if wait completed successfully
        """
        # Random initial delay to simulate human behavior
        initial_delay = min_delay_ms + int((max_delay_ms - min_delay_ms) * 0.3)
        await asyncio.sleep(initial_delay / 1000)
        
        # Wait for network idle if selector not specified
        if selector:
            try:
                await self.page.wait_for_selector(
                    selector,
                    timeout=10000,
                    state="visible",
                )
            except PlaywrightTimeout:
                logger.debug(f"Selector '{selector}' not found within timeout")
                return False
        
        # Wait for network to be idle
        try:
            await self.page.wait_for_load_state("networkidle", timeout=15000)
        except PlaywrightTimeout:
            logger.debug("Network idle timeout, continuing anyway")
        
        return True
    
    async def handle_cookie_consent(
        self,
        consent_type: Optional[CookieConsentType] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Handle cookie consent banner if present.
        
        Args:
            consent_type: Specific consent type to handle, or auto-detect if None
            
        Returns:
            Tuple of (handled, consent_type_found)
        """
        # Auto-detect consent type if not specified
        if consent_type is None:
            consent_type = await self._detect_cookie_consent()
        
        if consent_type == CookieConsentType.NONE:
            return False, None
        
        logger.debug(f"Detected cookie consent type: {consent_type.value}")
        
        try:
            if consent_type in (
                CookieConsentType.SIMPLE_ACCEPT,
                CookieConsentType.GDPR,
                CookieConsentType.CCPA,
            ):
                # Click accept button
                accepted = await self._click_accept_button()
                if accepted:
                    await asyncio.sleep(self.cookie_config.dismiss_delay_ms / 1000)
                    return True, consent_type.value
            
            elif consent_type == CookieConsentType.DETAILED:
                # For detailed consent, try to accept all
                await self._click_accept_button()
                await asyncio.sleep(0.5)
                await self._click_accept_button()  # Sometimes needs double click
                return True, consent_type.value
            
        except Exception as e:
            logger.warning(f"Error handling cookie consent: {e}")
        
        return False, consent_type.value if consent_type else None
    
    async def _detect_cookie_consent(self) -> CookieConsentType:
        """Detect type of cookie consent banner."""
        # Check for OneTrust (common GDPR banner)
        if await self.page.query_selector("#onetrust-consent-sdk"):
            return CookieConsentType.GDPR
        
        # Check for CCPA "Do Not Sell" banner
        if await self.page.query_selector("[aria-label*='Do Not Sell']"):
            return CookieConsentType.CCPA
        
        # Check for simple accept buttons
        for selector in self.cookie_config.accept_button_selectors[:3]:
            if await self.page.query_selector(selector):
                # Check if it's a modal with multiple options
                if await self.page.query_selector(
                    "[role='dialog'], .cookie-modal, #CybotCookiebotDialog"
                ):
                    return CookieConsentType.DETAILED
                return CookieConsentType.SIMPLE_ACCEPT
        
        # Check for any cookie-related elements
        cookie_elements = await self.page.query_selector_all(
            self.cookie_config.modal_selectors
        )
        if cookie_elements:
            return CookieConsentType.DETAILED
        
        return CookieConsentType.NONE
    
    async def _click_accept_button(self) -> bool:
        """Click the accept cookie button."""
        # Try each selector
        for selector in self.cookie_config.accept_button_selectors:
            try:
                button = await self.page.query_selector(selector)
                if button:
                    is_visible = await button.is_visible()
                    if is_visible:
                        await button.click(timeout=5000)
                        logger.debug(f"Clicked cookie accept button: {selector}")
                        return True
            except Exception as e:
                logger.debug(f"Selector {selector} failed: {e}")
                continue
        
        return False
    
    async def detect_captcha(self) -> Tuple[bool, Optional[str]]:
        """Detect if a captcha is present on the page.
        
        Returns:
            Tuple of (captcha_detected, captcha_type)
        """
        for selector in self.captcha_config.detection_selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    is_visible = await element.is_visible()
                    if is_visible:
                        # Determine captcha type from selector
                        if "recaptcha" in selector or "g-recaptcha" in selector:
                            return True, "recaptcha"
                        elif "hcaptcha" in selector:
                            return True, "hcaptcha"
                        elif "friendly-captcha" in selector:
                            return True, "friendly_captcha"
                        else:
                            return True, "unknown"
            except Exception:
                continue
        
        # Also check for captcha in page content
        captcha_text_selectors = [
            "text=/captcha/i",
            "text=/prove you are human/i",
            "text=/I am not a robot/i",
        ]
        
        for selector in captcha_text_selectors:
            try:
                if await self.page.query_selector(selector):
                    return True, "text_captcha"
            except Exception:
                continue
        
        return False, None
    
    async def solve_captcha_procedurally(
        self,
        captcha_type: str,
    ) -> Tuple[bool, Optional[str]]:
        """Attempt procedural captcha solving (limited effectiveness).
        
        Note: This is a best-effort approach. For production use,
        integrate with a captcha solving service (2Captcha, Anti-Captcha, etc.)
        
        Args:
            captcha_type: Type of captcha detected
            
        Returns:
            Tuple of (solved, solution_token)
        """
        logger.warning(
            f"Procedural captcha solving requested for {captcha_type}. "
            "This has limited effectiveness. Consider integrating a captcha service."
        )
        
        # For simple checkboxes (I'm not a robot)
        if captcha_type == "recaptcha":
            try:
                # Try clicking the recaptcha checkbox
                checkbox = await self.page.query_selector(
                    ".recaptcha-checkbox-checkmark"
                )
                if checkbox:
                    await checkbox.click()
                    await asyncio.sleep(2)
                    
                    # Check if it was solved
                    checked = await self.page.evaluate(
                        "document.querySelector('.recaptcha-checkbox-checked') !== null"
                    )
                    if checked:
                        return True, "checkbox_solved"
            except Exception as e:
                logger.warning(f"Recaptcha checkbox attempt failed: {e}")
        
        return False, None
    
    async def scroll_page(
        self,
        scroll_pause_ms: int = 500,
        max_scrolls: int = 10,
        scroll_distance: int = 500,
    ) -> int:
        """Scroll the page to trigger lazy-loaded content.
        
        Args:
            scroll_pause_ms: Pause between scrolls
            max_scrolls: Maximum number of scroll operations
            scroll_distance: Pixels to scroll per operation
            
        Returns:
            Number of scrolls performed
        """
        scrolls = 0
        last_height = await self.page.evaluate("document.body.scrollHeight")
        
        for i in range(max_scrolls):
            await self.page.evaluate(f"window.scrollBy(0, {scroll_distance})")
            await asyncio.sleep(scroll_pause_ms / 1000)
            
            new_height = await self.page.evaluate("document.body.scrollHeight")
            
            if new_height == last_height:
                # Try clicking "Load More" buttons
                load_more_clicked = await self._click_load_more()
                if load_more_clicked:
                    await asyncio.sleep(1000)
                    new_height = await self.page.evaluate("document.body.scrollHeight")
                    if new_height > last_height:
                        last_height = new_height
                        continue
            
            last_height = new_height
            scrolls += 1
        
        # Scroll back to top
        await self.page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(200)
        
        return scrolls
    
    async def _click_load_more(self) -> bool:
        """Click 'Load More' or similar buttons."""
        load_more_selectors = [
            "button:has-text('Load More')",
            "button:has-text('Show More')",
            "button:has-text('Load More Results')",
            "[aria-label*='Load More']",
            ".load-more",
            "#load-more",
        ]
        
        for selector in load_more_selectors:
            try:
                button = await self.page.query_selector(selector)
                if button and await button.is_visible():
                    await button.click(timeout=3000)
                    logger.debug(f"Clicked load more: {selector}")
                    return True
            except Exception:
                continue
        
        return False
    
    async def get_cookies(self) -> List[Dict[str, Any]]:
        """Get all cookies from current page context.
        
        Returns:
            List of cookie dictionaries
        """
        try:
            cookies = await self.page.context.cookies()
            return [
                {
                    "name": c["name"],
                    "value": c["value"],
                    "domain": c.get("domain", ""),
                    "path": c.get("path", "/"),
                    "expires": c.get("expires", -1),
                    "httpOnly": c.get("httpOnly", False),
                    "secure": c.get("secure", False),
                    "sameSite": c.get("sameSite", "Lax"),
                }
                for c in cookies
            ]
        except Exception as e:
            logger.warning(f"Error getting cookies: {e}")
            return []
    
    async def set_cookies(self, cookies: List[Dict[str, Any]]) -> bool:
        """Set cookies in current page context.
        
        Args:
            cookies: List of cookie dictionaries
            
        Returns:
            True if successful
        """
        try:
            # Playwright expects specific format
            await self.page.context.add_cookies(cookies)
            return True
        except Exception as e:
            logger.warning(f"Error setting cookies: {e}")
            return False
    
    async def take_screenshot(
        self,
        path: str,
        full_page: bool = False,
    ) -> bool:
        """Take a screenshot of the current page.
        
        Args:
            path: Path to save screenshot
            full_page: Capture full scrollable page
            
        Returns:
            True if successful
        """
        try:
            await self.page.screenshot(path=path, full_page=full_page)
            return True
        except Exception as e:
            logger.warning(f"Error taking screenshot: {e}")
            return False
    
    async def extract_text_content(
        self,
        selectors: List[str],
        join_with: str = "\n",
    ) -> str:
        """Extract text content from multiple selectors.
        
        Args:
            selectors: List of CSS selectors
            join_with: String to join multiple results
            
        Returns:
            Extracted text content
        """
        parts = []
        
        for selector in selectors:
            try:
                elements = await self.page.query_selector_all(selector)
                for element in elements:
                    text = await element.inner_text()
                    if text:
                        parts.append(text.strip())
            except Exception as e:
                logger.debug(f"Error extracting text from {selector}: {e}")
        
        return join_with.join(parts)
    
    async def evaluate_script(self, script: str) -> Any:
        """Execute JavaScript in page context.
        
        Args:
            script: JavaScript code to execute
            
        Returns:
            Result of script execution
        """
        try:
            return await self.page.evaluate(script)
        except Exception as e:
            logger.warning(f"Error evaluating script: {e}")
            return None
    
    @property
    def stats(self) -> Dict[str, int]:
        """Get interaction statistics."""
        return {
            "response_count": self._response_count,
            "error_count": self._error_count,
            "success_rate": (
                (self._response_count - self._error_count) / self._response_count
                if self._response_count > 0 else 1.0
            ),
        }
