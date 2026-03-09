"""Network interceptor - Capture HTTP traffic (browser-use style)"""

import asyncio
import json
import logging
import re
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import Page
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class RequestData(BaseModel):
    """HTTP Request data"""
    id: str
    url: str
    method: str
    headers: dict[str, str] = Field(default_factory=dict)
    post_data: str | None = None
    timestamp: datetime = Field(default_factory=datetime.now)


class ResponseData(BaseModel):
    """HTTP Response data"""
    id: str
    request_id: str
    status: int
    status_text: str
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    content_type: str | None = None
    timing: float | None = None


class NetworkEntry(BaseModel):
    """Complete network entry"""
    request: RequestData
    response: ResponseData | None = None
    duration: float | None = None


class NetworkRecorder:
    """
    Network traffic recorder with O(1) lookup performance.

    Captures HTTP/HTTPS requests and responses from browser.
    Uses OrderedDict for:
    - O(1) lookup by request_id
    - Maintains insertion order for iteration
    """

    def __init__(self):
        # OrderedDict for O(1) lookup + ordered iteration
        self._entries: OrderedDict[str, NetworkEntry] = OrderedDict()
        self._recording = False
        self._request_timestamps: dict[str, datetime] = {}

    @property
    def entries(self) -> list[NetworkEntry]:
        """Get entries as list (for backward compatibility)."""
        return list(self._entries.values())

    async def start(self, page: Page) -> None:
        """Start recording network traffic"""
        self._entries = OrderedDict()
        self._request_timestamps = {}
        self._recording = True

        # Setup request handler
        page.on("request", lambda request: asyncio.create_task(self._on_request(request)))

        # Setup response handler
        page.on("response", lambda response: asyncio.create_task(self._on_response(response)))

        logger.info("Network recording started")

    async def _on_request(self, request) -> None:
        """Handle request event"""
        if not self._recording:
            return

        request_id = request.url

        self._request_timestamps[request_id] = datetime.now()

        request_data = RequestData(
            id=request_id,
            url=request.url,
            method=request.method,
            headers=dict(request.headers),
            post_data=await self._get_post_data(request),
        )

        entry = NetworkEntry(request=request_data)
        self._entries[request_id] = entry  # O(1) insert

    async def _on_response(self, response) -> None:
        """Handle response event with O(1) lookup"""
        if not self._recording:
            return

        request_id = response.url

        # O(1) lookup instead of O(n) linear search
        entry = self._entries.get(request_id)
        if entry is None:
            return

        # Calculate duration
        start_time = self._request_timestamps.get(request_id)
        duration = None
        if start_time:
            duration = (datetime.now() - start_time).total_seconds() * 1000

        # Get response body
        body = None
        content_type = response.headers.get("content-type", "")

        try:
            if "application/json" in content_type or "text/" in content_type:
                body = await response.text()
        except Exception as e:
            logger.warning(f"Could not get response body: {e}")

        response_data = ResponseData(
            id=f"{request_id}_response",
            request_id=request_id,
            status=response.status,
            status_text=response.status_text,
            headers=dict(response.headers),
            body=body,
            content_type=content_type,
            timing=duration,
        )

        entry.response = response_data
        entry.duration = duration

    async def _get_post_data(self, request) -> str | None:
        """Get post data from request"""
        try:
            post_data = request.post_data
            if post_data:
                return post_data
        except Exception:
            pass
        return None

    async def stop(self) -> None:
        """Stop recording"""
        self._recording = False
        logger.info(f"Network recording stopped. Captured {len(self._entries)} requests")

    def get_requests(self) -> list[RequestData]:
        """Get all captured requests"""
        return [entry.request for entry in self._entries.values()]

    def get_responses(self) -> list[ResponseData]:
        """Get all captured responses"""
        return [entry.response for entry in self._entries.values() if entry.response]

    def get_entries(self) -> list[NetworkEntry]:
        """Get all network entries"""
        return list(self._entries.values())

    def get_entry_by_id(self, request_id: str) -> NetworkEntry | None:
        """Get entry by request_id with O(1) lookup."""
        return self._entries.get(request_id)

    def filter_by_url(self, pattern: str) -> list[NetworkEntry]:
        """Filter entries by URL pattern using compiled regex for performance."""
        try:
            regex = re.compile(pattern)
            return [e for e in self._entries.values() if regex.search(e.request.url)]
        except re.error:
            # Fallback to simple string match if regex is invalid
            return [e for e in self._entries.values() if pattern in e.request.url]

    def filter_by_method(self, method: str) -> list[NetworkEntry]:
        """Filter entries by HTTP method"""
        method_upper = method.upper()
        return [e for e in self._entries.values() if e.request.method.upper() == method_upper]

    def filter_by_status(self, status: int) -> list[NetworkEntry]:
        """Filter entries by status code"""
        return [e for e in self._entries.values() if e.response and e.response.status == status]

    def export_har(self, filepath: str | Path) -> None:
        """Export to HAR format"""
        har = {
            "log": {
                "version": "1.2",
                "creator": {"name": "VibeLens", "version": "0.2.0"},
                "entries": [],
            }
        }

        for entry in self._entries.values():
            har_entry = {
                "request": {
                    "method": entry.request.method,
                    "url": entry.request.url,
                    "headers": [
                        {"name": k, "value": v}
                        for k, v in entry.request.headers.items()
                    ],
                },
                "time": entry.duration or 0,
            }

            if entry.response:
                har_entry["response"] = {
                    "status": entry.response.status,
                    "statusText": entry.response.status_text,
                    "headers": [
                        {"name": k, "value": v}
                        for k, v in entry.response.headers.items()
                    ],
                    "content": {
                        "mimeType": entry.response.content_type or "",
                        "text": entry.response.body or "",
                    },
                }

            har["log"]["entries"].append(har_entry)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(har, f, indent=2)

        logger.info(f"Exported HAR to {filepath}")

    def clear(self) -> None:
        """Clear all captured entries"""
        self._entries = OrderedDict()
        self._request_timestamps = {}

    def __len__(self) -> int:
        """Return number of captured entries."""
        return len(self._entries)

    def __iter__(self):
        """Iterate over entries."""
        return iter(self._entries.values())
