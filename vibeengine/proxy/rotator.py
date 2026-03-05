"""Proxy rotator - Smart proxy rotation (Scrapling style)"""

import asyncio
import logging
import random
from enum import Enum
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ProxyStrategy(str, Enum):
    """Proxy rotation strategies"""
    CYCLIC = "cyclic"  # Rotate in order
    RANDOM = "random"  # Random selection
    SMART = "smart"  # Choose based on success rate


class ProxyRotator:
    """
    Smart proxy rotator with multiple strategies.

    Inspired by Scrapling's ProxyRotator.
    """

    def __init__(
        self,
        proxies: list[str] | None = None,
        strategy: ProxyStrategy = ProxyStrategy.CYCLIC,
        check_interval: int = 300,  # seconds
    ):
        self.proxies = proxies or []
        self.strategy = strategy
        self.check_interval = check_interval

        self._current_index = 0
        self._proxy_stats: dict[str, dict[str, Any]] = {}
        self._health_check_task: asyncio.Task | None = None

        # Initialize stats
        for proxy in self.proxies:
            self._proxy_stats[proxy] = {
                "success_count": 0,
                "failure_count": 0,
                "total_requests": 0,
                "last_used": None,
                "last_check": None,
                "is_healthy": True,
            }

    def add(self, proxy: str) -> None:
        """Add a proxy"""
        if proxy not in self.proxies:
            self.proxies.append(proxy)
            self._proxy_stats[proxy] = {
                "success_count": 0,
                "failure_count": 0,
                "total_requests": 0,
                "last_used": None,
                "last_check": None,
                "is_healthy": True,
            }

    def remove(self, proxy: str) -> None:
        """Remove a proxy"""
        if proxy in self.proxies:
            self.proxies.remove(proxy)
            self._proxy_stats.pop(proxy, None)

    def next(self) -> str | None:
        """Get next proxy based on strategy"""
        if not self.proxies:
            return None

        if self.strategy == ProxyStrategy.CYCLIC:
            proxy = self._cyclic_next()
        elif self.strategy == ProxyStrategy.RANDOM:
            proxy = self._random_next()
        elif self.strategy == ProxyStrategy.SMART:
            proxy = self._smart_next()
        else:
            proxy = self._cyclic_next()

        if proxy:
            self._proxy_stats[proxy]["last_used"] = asyncio.get_event_loop().time()

        return proxy

    def _cyclic_next(self) -> str | None:
        """Get next proxy in cyclic order"""
        if not self.proxies:
            return None

        proxy = self.proxies[self._current_index]
        self._current_index = (self._current_index + 1) % len(self.proxies)

        # Skip unhealthy proxies
        if not self._proxy_stats.get(proxy, {}).get("is_healthy", True):
            # Try next healthy proxy
            for _ in range(len(self.proxies)):
                proxy = self.proxies[self._current_index]
                self._current_index = (self._current_index + 1) % len(self.proxies)
                if self._proxy_stats.get(proxy, {}).get("is_healthy", True):
                    return proxy
            return None

        return proxy

    def _random_next(self) -> str | None:
        """Get random proxy"""
        if not self.proxies:
            return None

        # Filter healthy proxies
        healthy = [p for p in self.proxies if self._proxy_stats.get(p, {}).get("is_healthy", True)]

        if not healthy:
            return random.choice(self.proxies)

        return random.choice(healthy)

    def _smart_next(self) -> str | None:
        """Get proxy with best success rate"""
        if not self.proxies:
            return None

        # Filter healthy proxies and sort by success rate
        candidates = []
        for proxy in self.proxies:
            stats = self._proxy_stats.get(proxy, {})
            if stats.get("is_healthy", True):
                total = stats.get("total_requests", 1)
                success = stats.get("success_count", 0)
                success_rate = success / total if total > 0 else 0
                candidates.append((proxy, success_rate, stats.get("last_used", 0)))

        if not candidates:
            return random.choice(self.proxies)

        # Sort by success rate (desc) then by last used (asc - prefer less used)
        candidates.sort(key=lambda x: (-x[1], x[2]))

        return candidates[0][0]

    def record_success(self, proxy: str) -> None:
        """Record successful request"""
        if proxy in self._proxy_stats:
            self._proxy_stats[proxy]["success_count"] += 1
            self._proxy_stats[proxy]["total_requests"] += 1
            self._proxy_stats[proxy]["is_healthy"] = True

    def record_failure(self, proxy: str) -> None:
        """Record failed request"""
        if proxy in self._proxy_stats:
            self._proxy_stats[proxy]["failure_count"] += 1
            self._proxy_stats[proxy]["total_requests"] += 1

            # Mark as unhealthy if too many failures
            total = self._proxy_stats[proxy]["total_requests"]
            failures = self._proxy_stats[proxy]["failure_count"]
            if total >= 5 and failures / total > 0.5:
                self._proxy_stats[proxy]["is_healthy"] = False
                logger.warning(f"Proxy {proxy} marked as unhealthy")

    async def check_proxy(self, proxy: str, timeout: int = 10) -> bool:
        """Check if proxy is working"""
        try:
            response = httpx.get(
                "https://www.google.com",
                proxies={"http://": proxy, "https://": proxy},
                timeout=timeout,
            )
            is_healthy = response.status_code == 200
            self._proxy_stats[proxy]["last_check"] = asyncio.get_event_loop().time()
            self._proxy_stats[proxy]["is_healthy"] = is_healthy
            return is_healthy
        except Exception as e:
            logger.warning(f"Proxy check failed for {proxy}: {e}")
            self._proxy_stats[proxy]["is_healthy"] = False
            return False

    async def start_health_checks(self) -> None:
        """Start periodic health checks"""
        async def check_all():
            while True:
                await asyncio.sleep(self.check_interval)
                for proxy in self.proxies:
                    await self.check_proxy(proxy)

        self._health_check_task = asyncio.create_task(check_all())

    async def stop_health_checks(self) -> None:
        """Stop health checks"""
        if self._health_check_task:
            self._health_check_task.cancel()
            self._health_check_task = None

    def get_stats(self) -> dict[str, dict[str, Any]]:
        """Get proxy statistics"""
        return self._proxy_stats.copy()

    def get_healthy_proxies(self) -> list[str]:
        """Get list of healthy proxies"""
        return [p for p in self.proxies if self._proxy_stats.get(p, {}).get("is_healthy", True)]

    def __len__(self) -> int:
        return len(self.proxies)

    def __repr__(self) -> str:
        return f"ProxyRotator(proxies={len(self.proxies)}, strategy={self.strategy.value})"
