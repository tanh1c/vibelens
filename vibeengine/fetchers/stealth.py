"""Stealth fetcher - Bypass anti-bot systems (Scrapling style)"""

import asyncio
import logging
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import async_playwright, Browser, Page, BrowserContext

from vibeengine.fetchers.base import Fetcher, FetcherResponse

logger = logging.getLogger(__name__)


class StealthyFetcher:
    """
    Stealth fetcher with anti-bot bypass capabilities.

    Inspired by Scrapling's StealthyFetcher.
    Uses Playwright with stealth settings to bypass:
    - Cloudflare
    - Anti-bot detection
    - Fingerprinting
    """

    def __init__(
        self,
        headless: bool = True,
        solve_cloudflare: bool = False,
        proxy: str | None = None,
        user_agent: str | None = None,
        window_size: tuple[int, int] = (1280, 720),
    ):
        self.headless = headless
        self.solve_cloudflare = solve_cloudflare
        self.proxy = proxy
        self.user_agent = user_agent
        self.window_size = window_size

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
        """Start stealth browser"""
        self._playwright = await async_playwright().start()

        # Launch browser with stealth settings
        browser_type = self._playwright.chromium

        launch_options: dict[str, Any] = {
            "headless": self.headless,
            "args": self._get_stealth_args(),
        }

        # Proxy configuration
        if self.proxy:
            launch_options["proxy"] = {"server": self.proxy}

        self._browser = await browser_type.launch(**launch_options)

        # Create context with stealth settings
        context_options = self._get_stealth_context_options()
        self._context = await self._browser.new_context(**context_options)

        # Create initial page
        self._page = await self._context.new_page()

        logger.info("Stealth browser started")

    def _get_stealth_args(self) -> list[str]:
        """Get stealth browser arguments"""
        return [
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

    def _get_stealth_context_options(self) -> dict[str, Any]:
        """Get stealth context options"""
        options = {
            "viewport": {"width": self.window_size[0], "height": self.window_size[1]},
            "ignore_https_errors": True,
            "locale": "en-US",
            "timezone_id": "America/New_York",
            "permissions": ["geolocation", "notifications"],
            "extra_http_headers": {
                "Accept-Language": "en-US,en;q=0.9",
            },
        }

        if self.user_agent:
            options["user_agent"] = self.user_agent
        else:
            options["user_agent"] = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )

        return options

    async def fetch(self, url: str, wait_until: str = "networkidle") -> "StealthResponse":
        """Fetch a page with stealth mode"""
        if not self._page:
            await self.start()

        # Navigate to URL
        response = await self._page.goto(url, wait_until=wait_until)

        # Get content
        content = await self._page.content()
        url = self._page.url

        return StealthResponse(
            url=url,
            content=content,
            status=response.status if response else 200,
            headers=await self._page.evaluate("() => JSON.stringify(window.headers || {})"),
        )

    async def fetch_with_wait(
        self,
        url: str,
        selector: str | None = None,
        timeout: int = 30000,
    ) -> "StealthResponse":
        """Fetch page and wait for selector"""
        if not self._page:
            await self.start()

        try:
            response = await self._page.goto(url, wait_until="domcontentloaded", timeout=timeout)

            if selector:
                await self._page.wait_for_selector(selector, timeout=timeout)

            content = await self._page.content()
            url = self._page.url

            return StealthResponse(
                url=url,
                content=content,
                status=response.status if response else 200,
            )
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return StealthResponse(
                url=url,
                content="",
                status=0,
                error=str(e),
            )

    async def evaluate(self, script: str) -> Any:
        """Execute JavaScript"""
        if not self._page:
            raise RuntimeError("Browser not started")
        return await self._page.evaluate(script)

    async def click(self, selector: str) -> None:
        """Click element"""
        if not self._page:
            raise RuntimeError("Browser not started")
        await self._page.click(selector)

    async def type(self, selector: str, text: str) -> None:
        """Type text into element"""
        if not self._page:
            raise RuntimeError("Browser not started")
        await self._page.fill(selector, text)

    async def screenshot(self, path: str | None = None) -> bytes:
        """Take screenshot"""
        if not self._page:
            raise RuntimeError("Browser not started")
        return await self._page.screenshot(path=path)

    async def close(self) -> None:
        """Close the browser"""
        if self._page:
            await self._page.close()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

        logger.info("Stealth browser closed")

    @staticmethod
    def create() -> "StealthyFetcher":
        """Create a new stealth fetcher"""
        return StealthyFetcher()


class StealthResponse:
    """Response from stealth fetcher"""

    def __init__(
        self,
        url: str,
        content: str,
        status: int = 200,
        headers: str | dict | None = None,
        error: str | None = None,
    ):
        self.url = url
        self.content = content
        self.status = status
        self.error = error

        if isinstance(headers, str):
            import json
            try:
                self.headers = json.loads(headers)
            except Exception:
                self.headers = {}
        else:
            self.headers = headers or {}

    @property
    def text(self) -> str:
        return self.content

    @property
    def html(self) -> str:
        return self.content

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def css(self, selector: str) -> list["StealthElement"]:
        """CSS selector (placeholder - needs parser integration)"""
        return []

    def xpath(self, selector: str) -> list["StealthElement"]:
        """XPath selector (placeholder)"""
        return []


class StealthElement:
    """Element from stealth response"""
    pass
