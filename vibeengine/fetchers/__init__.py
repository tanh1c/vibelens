"""Fetchers module - HTTP fetching with stealth capabilities (Scrapling style)"""

from vibeengine.fetchers.base import Fetcher
from vibeengine.fetchers.stealth import StealthyFetcher
from vibeengine.fetchers.dynamic import DynamicFetcher

__all__ = [
    "Fetcher",
    "StealthyFetcher",
    "DynamicFetcher",
]
