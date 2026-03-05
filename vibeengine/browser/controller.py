"""Browser controller using CDP (Chrome DevTools Protocol) - browser-use style"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Literal, Self
from urllib.parse import urlparse

from playwright.async_api import async_playwright, Browser, Page, BrowserContext, Playwright
from pydantic import BaseModel, Field, PrivateAttr

from vibeengine.browser.views import BrowserConfig, PageInfo, ElementInfo, ProxySettings

logger = logging.getLogger(__name__)


class Browser:
    """
    Browser controller using CDP via Playwright.

    Inspired by browser-use architecture but simplified for VibeLens.
    """

    def __init__(
        self,
        headless: bool | None = None,
        browser: str = "chromium",
        proxy: ProxySettings | None = None,
        user_agent: str | None = None,
        window_size: dict[str, int] | None = None,
        record_har_path: str | None = None,
        **kwargs: Any,
    ):
        self.config = BrowserConfig(
            headless=headless,
            browser=browser,
            proxy=proxy,
            user_agent=user_agent,
            window_size=window_size or {"width": 1280, "height": 720},
            record_har_path=record_har_path,
        )

        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def start(self) -> None:
        """Start the browser"""
        self._playwright = await async_playwright().start()

        browser_type = getattr(self._playwright, self.config.browser)

        launch_options: dict[str, Any] = {
            "headless": self.config.headless if self.config.headless is not None else True,
        }

        # Proxy configuration
        if self.config.proxy:
            proxy: dict[str, str] = {"server": self.config.proxy.server}
            if self.config.proxy.username and self.config.proxy.password:
                proxy["username"] = self.config.proxy.username
                proxy["password"] = self.config.proxy.password
            launch_options["proxy"] = proxy

        # Launch browser
        self._browser = await browser_type.launch(**launch_options)

        # Create context with options
        context_options: dict[str, Any] = {
            "viewport": self.config.window_size,
            "ignore_https_errors": True,
        }

        if self.config.user_agent:
            context_options["user_agent"] = self.config.user_agent

        if self.config.record_har_path:
            context_options["record_har_path"] = self.config.record_har_path
            context_options["record_har_url_filter"] = ".*"

        self._context = await self._browser.new_context(**context_options)

        # Create initial page
        self._page = await self._context.new_page()

        logger.info(f"Browser started: {self.config.browser} (headless={self.config.headless})")

    async def new_page(self) -> Page:
        """Create a new page/tab"""
        if not self._context:
            raise RuntimeError("Browser not started")
        return await self._context.new_page()

    @property
    def page(self) -> Page:
        """Get the current page"""
        if not self._page:
            raise RuntimeError("No active page")
        return self._page

    async def goto(self, url: str, **kwargs: Any) -> None:
        """Navigate to URL"""
        await self.page.goto(url, **kwargs)

    async def click(self, selector: str) -> None:
        """Click element by selector"""
        await self.page.click(selector)

    async def type(self, selector: str, text: str, delay: int = 0) -> None:
        """Type text into element"""
        await self.page.fill(selector, text, delay=delay)

    async def scroll(self, direction: str = "down", amount: int = 500) -> None:
        """Scroll the page"""
        if direction == "down":
            await self.page.evaluate(f"window.scrollBy(0, {amount})")
        else:
            await self.page.evaluate(f"window.scrollBy(0, -{amount})")

    async def screenshot(self, path: str | None = None, full_page: bool = False) -> bytes | str:
        """Take screenshot"""
        return await self.page.screenshot(path=path, full_page=full_page)

    async def get_html(self) -> str:
        """Get page HTML"""
        return await self.page.content()

    async def get_title(self) -> str:
        """Get page title"""
        return await self.page.title()

    async def get_url(self) -> str:
        """Get current URL"""
        return self.page.url

    async def wait_for_selector(self, selector: str, timeout: int = 30000) -> bool:
        """Wait for selector"""
        try:
            await self.page.wait_for_selector(selector, timeout=timeout)
            return True
        except Exception:
            return False

    async def evaluate(self, script: str) -> Any:
        """Execute JavaScript"""
        return await self.page.evaluate(script)

    async def get_clickable_elements(self) -> list[ElementInfo]:
        """Get clickable elements on the page"""
        elements = await self.page.evaluate("""
            () => {
                const elements = [];
                const tags = ['a', 'button', 'input', 'select', 'textarea', 'label'];

                document.querySelectorAll(tags.join(', ')).forEach((el, index) => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        elements.push({
                            index: index,
                            tag: el.tagName.toLowerCase(),
                            text: el.innerText?.substring(0, 100) || null,
                            attributes: {
                                type: el.type,
                                name: el.name,
                                id: el.id,
                                class: el.className,
                                href: el.href,
                                action: el.form?.action
                            },
                            is_visible: rect.top >= 0 && rect.left >= 0
                        });
                    }
                });
                return elements;
            }
        """)

        return [ElementInfo(**el) for el in elements]

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

        logger.info("Browser closed")


# Alias for backward compatibility
BrowserSession = Browser
