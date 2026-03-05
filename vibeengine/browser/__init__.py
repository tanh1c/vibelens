"""Browser module - CDP-based browser control (browser-use style)"""

from vibeengine.browser.controller import Browser, BrowserSession
from vibeengine.browser.views import BrowserConfig, PageInfo, ElementInfo

__all__ = [
    "Browser",
    "BrowserSession",
    "BrowserConfig",
    "PageInfo",
    "ElementInfo",
]
