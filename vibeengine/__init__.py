"""
VibeLens - AI-Powered Browser Automation & API Testing Platform

A library combining browser automation with network analysis for API testing.
"""

__version__ = "0.1.0"

from vibeengine.browser import Browser, BrowserSession
from vibeengine.agent import Agent
from vibeengine.network import NetworkRecorder, NetworkAnalyzer
from vibeengine.fetchers import Fetcher, StealthyFetcher, DynamicFetcher
from vibeengine.proxy import ProxyRotator
from vibeengine.parser import Selector

__all__ = [
    "__version__",
    "Browser",
    "BrowserSession",
    "Agent",
    "NetworkRecorder",
    "NetworkAnalyzer",
    "Fetcher",
    "StealthyFetcher",
    "DynamicFetcher",
    "ProxyRotator",
    "Selector",
]
