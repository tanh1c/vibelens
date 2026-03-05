"""Base fetcher - HTTP fetching with session support (Scrapling style)"""

import logging
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


class Fetcher:
    """
    HTTP fetcher with session support.

    Inspired by Scrapling's Fetcher class.
    """

    def __init__(
        self,
        impersonate: str = "chrome",
        proxy: str | None = None,
        timeout: int = 30,
        headers: dict[str, str] | None = None,
    ):
        self.impersonate = impersonate
        self.proxy = proxy
        self.timeout = timeout
        self.headers = headers or {}
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None:
            self._client = self._create_client()
        return self._client

    def _create_client(self) -> httpx.AsyncClient:
        """Create HTTP client with impersonation"""
        # Browser fingerprint headers
        default_headers = self._get_browser_headers(self.impersonate)
        default_headers.update(self.headers)

        # Proxy transport if needed
        transport: Any = None
        if self.proxy:
            transport = httpx.AsyncHTTPTransport(proxy=self.proxy)

        return httpx.AsyncClient(
            timeout=self.timeout,
            headers=default_headers,
            transport=transport,
            follow_redirects=True,
        )

    def _get_browser_headers(self, browser: str) -> dict[str, str]:
        """Get browser fingerprint headers"""
        browsers = {
            "chrome": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
            },
            "firefox": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            },
        }
        return browsers.get(browser, browsers["chrome"])

    async def get(self, url: str, **kwargs: Any) -> "FetcherResponse":
        """GET request"""
        response = await self.client.get(url, **kwargs)
        return FetcherResponse(response)

    async def post(
        self,
        url: str,
        data: Any = None,
        json: Any = None,
        **kwargs: Any,
    ) -> "FetcherResponse":
        """POST request"""
        response = await self.client.post(url, data=data, json=json, **kwargs)
        return FetcherResponse(response)

    async def put(
        self,
        url: str,
        data: Any = None,
        json: Any = None,
        **kwargs: Any,
    ) -> "FetcherResponse":
        """PUT request"""
        response = await self.client.put(url, data=data, json=json, **kwargs)
        return FetcherResponse(response)

    async def delete(self, url: str, **kwargs: Any) -> "FetcherResponse":
        """DELETE request"""
        response = await self.client.delete(url, **kwargs)
        return FetcherResponse(response)

    async def fetch(self, url: str, **kwargs: Any) -> "FetcherResponse":
        """Generic fetch - automatically choose method"""
        response = await self.client.request("GET", url, **kwargs)
        return FetcherResponse(response)

    async def close(self) -> None:
        """Close the client"""
        if self._client:
            await self._client.aclose()
            self._client = None


class FetcherResponse:
    """Response from Fetcher"""

    def __init__(self, response: httpx.Response):
        self._response = response

    @property
    def status_code(self) -> int:
        return self._response.status_code

    @property
    def text(self) -> str:
        return self._response.text

    @property
    def content(self) -> bytes:
        return self._response.content

    @property
    def headers(self) -> dict[str, str]:
        return dict(self._response.headers)

    @property
    def url(self) -> str:
        return str(self._response.url)

    def json(self) -> Any:
        return self._response.json()

    @property
    def html(self) -> str:
        """Get HTML content"""
        return self.text

    def css(self, selector: str, **kwargs: Any) -> list[Any]:
        """CSS selector (requires parser)"""
        # Will be enhanced with parser integration
        return []

    def xpath(self, selector: str) -> list[Any]:
        """XPath selector (requires parser)"""
        return []
