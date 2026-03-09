"""
Stealth fetcher - Bypass anti-bot systems using playwright-stealth.

Benefits of playwright-stealth over manual configuration:
- Automatically applies all anti-detection techniques
- Regularly updated with latest bypass methods
- Handles fingerprint randomization
- Mimics real browser behavior
"""

import asyncio
import json
import logging
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from vibeengine.parser.selector import Selector

logger = logging.getLogger(__name__)

# Lazy check for playwright-stealth (only warn when actually used, not at import time)
STEALTH_AVAILABLE = None  # None = not checked yet


def _check_stealth() -> bool:
    """Lazy check if playwright-stealth is available."""
    global STEALTH_AVAILABLE
    if STEALTH_AVAILABLE is None:
        try:
            from playwright_stealth import stealth_async  # noqa: F401
            STEALTH_AVAILABLE = True
        except ImportError:
            STEALTH_AVAILABLE = False
    return STEALTH_AVAILABLE


class StealthyFetcher:
    """
    Stealth fetcher with comprehensive anti-bot bypass capabilities.

    Uses playwright-stealth for automatic anti-detection:
    - Cloudflare bypass
    - Bot detection evasion
    - Fingerprint randomization
    - WebDriver detection hiding
    """

    # Default stealth browser arguments
    STEALTH_ARGS = [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--disable-accelerated-2d-canvas",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-gpu",
        "--no-zygote",
        "--disable-web-security",
        "--disable-features=IsolateOrigins,site-per-process",
    ]

    # Default user agent (Chrome 120 on Windows)
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        headless: bool = True,
        solve_cloudflare: bool = False,
        proxy: str | None = None,
        user_agent: str | None = None,
        window_size: tuple[int, int] = (1280, 720),
        timeout: int = 30000,
    ):
        self.headless = headless
        self.solve_cloudflare = solve_cloudflare
        self.proxy = proxy
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT
        self.window_size = window_size
        self.timeout = timeout

        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def __aenter__(self) -> "StealthyFetcher":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def start(self) -> None:
        """Start stealth browser with anti-detection measures."""
        self._playwright = await async_playwright().start()

        launch_options: dict[str, Any] = {
            "headless": self.headless,
            "args": self.STEALTH_ARGS,
        }

        if self.proxy:
            launch_options["proxy"] = {"server": self.proxy}

        self._browser = await self._playwright.chromium.launch(**launch_options)

        # Create context with stealth settings
        context_options = {
            "viewport": {"width": self.window_size[0], "height": self.window_size[1]},
            "ignore_https_errors": True,
            "locale": "en-US",
            "timezone_id": "America/New_York",
            "user_agent": self.user_agent,
            "permissions": ["geolocation", "notifications"],
            "extra_http_headers": {
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            },
        }

        self._context = await self._browser.new_context(**context_options)
        self._page = await self._context.new_page()

        # Apply playwright-stealth if available (lazy check)
        if _check_stealth():
            from playwright_stealth import stealth_async
            await stealth_async(self._page)
            logger.info("Stealth browser started with playwright-stealth")
        else:
            await self._apply_manual_stealth()
            logger.info("Stealth browser started with manual stealth settings")

    async def _apply_manual_stealth(self) -> None:
        """Apply manual stealth scripts when playwright-stealth is not available."""
        # Hide webdriver property
        await self._page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        # Mock plugins
        await self._page.add_init_script("""
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
        """)

        # Mock languages
        await self._page.add_init_script("""
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
        """)

        # Hide automation indicators
        await self._page.add_init_script("""
            window.chrome = {
                runtime: {}
            };
        """)

        # Mock permissions
        await self._page.add_init_script("""
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
        """)

    async def fetch(self, url: str, wait_until: str = "networkidle") -> "StealthResponse":
        """Fetch a page with stealth mode."""
        if not self._page:
            await self.start()

        try:
            response = await self._page.goto(url, wait_until=wait_until, timeout=self.timeout)

            # Wait for Cloudflare challenge if enabled
            if self.solve_cloudflare:
                await self._wait_for_cloudflare()

            content = await self._page.content()
            final_url = self._page.url

            return StealthResponse(
                url=final_url,
                content=content,
                status=response.status if response else 200,
                page=self._page,
            )
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return StealthResponse(url=url, content="", status=0, error=str(e))

    async def _wait_for_cloudflare(self, timeout: int = 30000) -> None:
        """Wait for Cloudflare challenge to complete."""
        try:
            # Wait for Cloudflare challenge to disappear
            await self._page.wait_for_function(
                """() => {
                    const cfChallenge = document.querySelector('#challenge-running');
                    return !cfChallenge;
                }""",
                timeout=timeout,
            )
        except Exception:
            logger.warning("Cloudflare challenge timeout or not detected")

    async def fetch_with_wait(
        self,
        url: str,
        selector: str | None = None,
        timeout: int = 30000,
    ) -> "StealthResponse":
        """Fetch page and wait for selector."""
        if not self._page:
            await self.start()

        try:
            response = await self._page.goto(url, wait_until="domcontentloaded", timeout=timeout)

            if selector:
                await self._page.wait_for_selector(selector, timeout=timeout)

            if self.solve_cloudflare:
                await self._wait_for_cloudflare()

            content = await self._page.content()
            final_url = self._page.url

            return StealthResponse(
                url=final_url,
                content=content,
                status=response.status if response else 200,
                page=self._page,
            )
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return StealthResponse(url=url, content="", status=0, error=str(e))

    async def evaluate(self, script: str) -> Any:
        """Execute JavaScript."""
        if not self._page:
            raise RuntimeError("Browser not started")
        return await self._page.evaluate(script)

    async def click(self, selector: str) -> None:
        """Click element."""
        if not self._page:
            raise RuntimeError("Browser not started")
        await self._page.click(selector)

    async def type(self, selector: str, text: str) -> None:
        """Type text into element."""
        if not self._page:
            raise RuntimeError("Browser not started")
        await self._page.fill(selector, text)

    async def screenshot(self, path: str | None = None) -> bytes:
        """Take screenshot."""
        if not self._page:
            raise RuntimeError("Browser not started")
        return await self._page.screenshot(path=path)

    @property
    def page(self) -> Page:
        """Get the current page."""
        if not self._page:
            raise RuntimeError("Browser not started")
        return self._page

    async def close(self) -> None:
        """Close the browser."""
        if self._page:
            await self._page.close()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

        logger.info("Stealth browser closed")

    @staticmethod
    def create() -> "StealthyFetcher":
        """Create a new stealth fetcher."""
        return StealthyFetcher()


class StealthResponse:
    """Response from stealth fetcher with integrated selector."""

    def __init__(
        self,
        url: str,
        content: str,
        status: int = 200,
        headers: str | dict | None = None,
        error: str | None = None,
        page: Page | None = None,
    ):
        self.url = url
        self.content = content
        self.status = status
        self.error = error
        self._page = page

        if isinstance(headers, str):
            try:
                self.headers = json.loads(headers)
            except json.JSONDecodeError:
                self.headers = {}
        else:
            self.headers = headers or {}

        # Lazy-loaded selector
        self._selector: Selector | None = None

    @property
    def text(self) -> str:
        return self.content

    @property
    def html(self) -> str:
        return self.content

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    @property
    def selector(self) -> Selector:
        """Get a Selector for parsing the response content."""
        if self._selector is None:
            self._selector = Selector(self.content, base_url=self.url)
        return self._selector

    def css(self, selector: str) -> list:
        """CSS selector using integrated Selector."""
        return self.selector.css(selector)

    def xpath(self, selector: str) -> list:
        """XPath selector using integrated Selector."""
        return self.selector.xpath(selector)

    def get_links(self) -> list[dict[str, str]]:
        """Extract all links from the page."""
        return self.selector.get_all_links()

    def get_images(self) -> list[dict[str, str]]:
        """Extract all images from the page."""
        return self.selector.get_images()

    def get_forms(self) -> list[dict[str, Any]]:
        """Extract all forms from the page."""
        return self.selector.get_forms()

    def __repr__(self) -> str:
        return f"<StealthResponse url={self.url} status={self.status}>"