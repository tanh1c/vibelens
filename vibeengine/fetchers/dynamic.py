"""Dynamic fetcher - Full browser automation with Playwright (Scrapling style)"""

import asyncio
import logging
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import async_playwright, Browser, Page, BrowserContext

logger = logging.getLogger(__name__)


class DynamicFetcher:
    """
    Dynamic content fetcher using Playwright.

    Inspired by Scrapling's DynamicFetcher.
    Handles JavaScript-rendered content.
    """

    def __init__(
        self,
        headless: bool = True,
        proxy: str | None = None,
        user_agent: str | None = None,
        window_size: tuple[int, int] = (1280, 720),
        disable_resources: bool = False,
        network_idle: bool = True,
    ):
        self.headless = headless
        self.proxy = proxy
        self.user_agent = user_agent
        self.window_size = window_size
        self.disable_resources = disable_resources
        self.network_idle = network_idle

        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def __aenter__(self) -> "DynamicFetcher":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def start(self) -> None:
        """Start browser"""
        self._playwright = await async_playwright().start()
        browser_type = self._playwright.chromium

        launch_options: dict[str, Any] = {
            "headless": self.headless,
        }

        if self.proxy:
            launch_options["proxy"] = {"server": self.proxy}

        self._browser = await browser_type.launch(**launch_options)

        context_options: dict[str, Any] = {
            "viewport": {"width": self.window_size[0], "height": self.window_size[1]},
            "ignore_https_errors": True,
        }

        if self.user_agent:
            context_options["user_agent"] = self.user_agent

        self._context = await self._browser.new_context(**context_options)

        # Block resources if requested
        if self.disable_resources:
            await self._context.route("**/*", self._block_resource)

        self._page = await self._context.new_page()

        logger.info("Dynamic fetcher started")

    async def _block_resource(self, route):
        """Block unnecessary resources"""
        if route.request.resource_type in ["image", "stylesheet", "font", "media"]:
            await route.abort()
        else:
            await route.continue_()

    async def fetch(
        self,
        url: str,
        load_dom: bool = True,
        wait_until: str = "networkidle",
    ) -> "DynamicResponse":
        """Fetch a page"""
        if not self._page:
            await self.start()

        wait = "networkidle" if self.network_idle else "load"

        response = await self._page.goto(url, wait_until=wait)
        content = await self._page.content()

        return DynamicResponse(
            url=self._page.url,
            content=content,
            status=response.status if response else 200,
        )

    async def fetch_and_wait(
        self,
        url: str,
        selector: str | None = None,
        timeout: int = 30000,
    ) -> "DynamicResponse":
        """Fetch page and wait for selector"""
        if not self._page:
            await self.start()

        response = await self._page.goto(url, wait_until="domcontentloaded", timeout=timeout)

        if selector:
            await self._page.wait_for_selector(selector, timeout=timeout)

        content = await self._page.content()

        return DynamicResponse(
            url=self._page.url,
            content=content,
            status=response.status if response else 200,
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
        """Type text"""
        if not self._page:
            raise RuntimeError("Browser not started")
        await self._page.fill(selector, text)

    async def scroll(self, direction: str = "down", amount: int = 500) -> None:
        """Scroll page"""
        if not self._page:
            raise RuntimeError("Browser not started")

        if direction == "down":
            await self._page.evaluate(f"window.scrollBy(0, {amount})")
        else:
            await self._page.evaluate(f"window.scrollBy(0, -{amount})")

    async def screenshot(self, path: str | None = None) -> bytes:
        """Take screenshot"""
        if not self._page:
            raise RuntimeError("Browser not started")
        return await self._page.screenshot(path=path)

    async def close(self) -> None:
        """Close browser"""
        if self._page:
            await self._page.close()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

        logger.info("Dynamic fetcher closed")

    @staticmethod
    def create() -> "DynamicFetcher":
        """Create new fetcher"""
        return DynamicFetcher()


class DynamicResponse:
    """Response from dynamic fetcher"""

    def __init__(self, url: str, content: str, status: int = 200):
        self.url = url
        self.content = content
        self.status = status

    @property
    def text(self) -> str:
        return self.content

    @property
    def html(self) -> str:
        return self.content

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def css(self, selector: str) -> list["DynamicElement"]:
        """CSS selector (placeholder)"""
        return []

    def xpath(self, selector: str) -> list["DynamicElement"]:
        """XPath selector (placeholder)"""
        return []


class DynamicElement:
    """Element from dynamic response"""
    pass
