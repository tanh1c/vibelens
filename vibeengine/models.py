"""Type definitions for VibeLens"""

from typing import Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime


class RequestModel(BaseModel):
    """HTTP Request model"""
    id: str
    url: str
    method: str
    headers: dict[str, str] = Field(default_factory=dict)
    post_data: str | None = None
    timestamp: datetime = Field(default_factory=datetime.now)


class ResponseModel(BaseModel):
    """HTTP Response model"""
    id: str
    request_id: str
    status: int
    status_text: str
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    content_type: str | None = None
    timing: float | None = None  # milliseconds


class NetworkEntry(BaseModel):
    """Complete network entry with request and response"""
    request: RequestModel
    response: ResponseModel | None = None
    duration: float | None = None  # milliseconds


class ProxySettings(BaseModel):
    """Proxy configuration"""
    server: str
    username: str | None = None
    password: str | None = None
    bypass: str | None = None


class BrowserConfig(BaseModel):
    """Browser configuration"""
    headless: bool = True
    window_size: dict[str, int] = Field(
        default_factory=lambda: {"width": 1280, "height": 720}
    )
    user_agent: str | None = None
    proxy: ProxySettings | None = None
    record_har: bool = False
    har_path: str | None = None


class ActionResult(BaseModel):
    """Result from a browser action"""
    success: bool
    extracted_content: str | None = None
    error: str | None = None
    is_done: bool = False


class AgentHistory(BaseModel):
    """Agent execution history"""
    urls: list[str] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    screenshots: list[str] = Field(default_factory=list)  # base64
    extracted_content: list[str] = Field(default_factory=list)
    errors: list[str | None] = Field(default_factory=list)
