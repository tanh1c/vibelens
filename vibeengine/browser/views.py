"""Browser data models (Pydantic) - browser-use style"""

from typing import Any
from pydantic import BaseModel, Field
from datetime import datetime


class ViewportSize(BaseModel):
    """Viewport dimensions"""
    width: int = 1280
    height: int = 720


class ProxySettings(BaseModel):
    """Proxy configuration"""
    server: str
    username: str | None = None
    password: str | None = None
    bypass: str | None = None


class BrowserProfile(BaseModel):
    """Browser profile settings"""
    user_data_dir: str | None = None
    profile_directory: str = "Default"
    storage_state: dict[str, Any] | None = None


class BrowserConfig(BaseModel):
    """Browser configuration"""
    headless: bool | None = None  # None = auto-detect
    window_size: ViewportSize = Field(default_factory=ViewportSize)
    viewport: ViewportSize | None = None
    user_agent: str | None = None
    proxy: ProxySettings | None = None
    browser: str = "chromium"  # chromium, firefox, webkit
    channel: str | None = None  # chrome, msedge, etc.
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    devtools: bool = False
    keep_alive: bool = False
    record_video_dir: str | None = None
    record_har_path: str | None = None
    downloads_path: str | None = None
    permissions: list[str] = Field(
        default_factory=lambda: ["clipboard-read-write", "notifications"]
    )


class ElementInfo(BaseModel):
    """Clickable element information"""
    index: int
    tag: str
    text: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    xpath: str | None = None
    css_selector: str | None = None
    is_visible: bool = True
    is_interactive: bool = True


class PageInfo(BaseModel):
    """Page information"""
    url: str
    title: str | None = None
    elements: list[ElementInfo] = Field(default_factory=list)
    html: str | None = None


class BrowserState(BaseModel):
    """Current browser state"""
    page: PageInfo
    tabs: list[str] = Field(default_factory=list)
    current_tab: str | None = None
    browser_id: str | None = None
