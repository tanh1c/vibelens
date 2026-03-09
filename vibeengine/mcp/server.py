"""
VibeLens MCP Server
Provides network requests to AI agents via Model Context Protocol
"""

import os
import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from vibeengine.smart_filter import (
    classify_request as hybrid_classify,
    classify_requests_batch,
    get_filtered_requests as hybrid_filter_requests,
    get_engine_info,
)

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from vibeengine.llm import ChatOpenAI, ChatAnthropic
from vibeengine.mcp.database import (
    create_session, save_requests, save_metadata, 
    get_recent_sessions, get_session_requests, get_session_metadata,
    delete_request, delete_requests_bulk, delete_session
)

# Load .env file BEFORE reading config
_env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(_env_path)

# Read config AFTER loading .env
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "dashscope")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-plus")
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")

app = FastAPI(title="VibeLens MCP Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store captured requests
requests_store: list[dict[str, Any]] = []

# Blueprints store
blueprints_store: list[dict[str, Any]] = []

# Scheduled watches
scheduled_watches: list[dict[str, Any]] = []

# Capture metadata (cookies, domains)
capture_meta: dict[str, Any] = {}

# Masking config
MASKING_ENABLED = True
SENSITIVE_HEADERS = [
    "authorization", "cookie", "set-cookie", "x-csrf-token",
    "x-api-key", "api-key", "x-auth-token", "proxy-authorization",
    "www-authenticate", "x-session-id", "x-access-token",
]
SENSITIVE_BODY_KEYS = [
    "password", "passwd", "secret", "token", "api_key", "apikey",
    "access_token", "refresh_token", "credit_card", "cvv", "ssn",
]

# Provider configs (already loaded from .env above)
DASHSCOPE_OPENAI_URL = "https://coding-intl.dashscope.aliyuncs.com/v1"
DASHSCOPE_ANTHROPIC_URL = "https://coding-intl.dashscope.aliyuncs.com/apps/anthropic"


# ─── Sensitive Data Masking Engine ───
def mask_value(value: str, show_chars: int = 4) -> str:
    """Mask a sensitive value, showing only first few chars"""
    if not value or len(value) <= show_chars:
        return "***"
    return value[:show_chars] + "***" + value[-2:] if len(value) > 6 else value[:show_chars] + "***"


def mask_headers(headers: dict[str, str]) -> dict[str, str]:
    """Mask sensitive headers"""
    if not MASKING_ENABLED or not headers:
        return headers
    masked = {}
    for key, value in headers.items():
        if key.lower() in SENSITIVE_HEADERS:
            masked[key] = mask_value(str(value))
        else:
            masked[key] = value
    return masked


def mask_body(body: str | None) -> str | None:
    """Mask sensitive fields in request body"""
    if not MASKING_ENABLED or not body:
        return body
    try:
        data = json.loads(body)
        if isinstance(data, dict):
            for key in data:
                if key.lower() in SENSITIVE_BODY_KEYS:
                    data[key] = mask_value(str(data[key]))
            return json.dumps(data)
    except (json.JSONDecodeError, TypeError):
        pass
    return body


def mask_request(req: dict[str, Any]) -> dict[str, Any]:
    """Apply masking to a full request object"""
    if not MASKING_ENABLED:
        return req
    masked = dict(req)
    if masked.get("headers"):
        masked["headers"] = mask_headers(masked["headers"])
    if masked.get("responseHeaders"):
        masked["responseHeaders"] = mask_headers(masked["responseHeaders"])
    if masked.get("postData") and isinstance(masked["postData"], str):
        masked["postData"] = mask_body(masked["postData"])
    return masked


class AnalyzeRequest(BaseModel):
    requests: list[dict[str, Any]] = []
    prompt: str | None = None


class MCPRequest(BaseModel):
    method: str
    params: dict[str, Any] | None = None


def get_llm(provider: str = None):
    """Get LLM instance based on provider"""
    provider = provider or LLM_PROVIDER

    if provider == "dashscope":
        # Use DashScope with OpenAI-compatible API
        return ChatOpenAI(
            model=LLM_MODEL,
            api_key=DASHSCOPE_API_KEY,
            base_url=DASHSCOPE_OPENAI_URL,
        )
    elif provider == "anthropic":
        return ChatAnthropic(
            model="claude-sonnet-4-20250514",
        )
    else:
        # Default to OpenAI
        return ChatOpenAI(model=LLM_MODEL)


@app.get("/")
async def root():
    return {
        "name": "VibeLens MCP Server",
        "version": "0.2.0",
        "status": "running",
        "provider": LLM_PROVIDER,
        "model": LLM_MODEL,
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/config")
async def get_config():
    """Get current configuration"""
    return {
        "provider": LLM_PROVIDER,
        "model": LLM_MODEL,
        "dashscope_configured": bool(DASHSCOPE_API_KEY),
        "raw_key": DASHSCOPE_API_KEY,
        "env_path": str(_env_path)
    }


@app.post("/config")
async def update_config(data: dict[str, Any]):
    """Update LLM configuration"""
    global LLM_PROVIDER, LLM_MODEL

    if "provider" in data:
        LLM_PROVIDER = data["provider"]
    if "model" in data:
        LLM_MODEL = data["model"]

    return {"status": "ok", "provider": LLM_PROVIDER, "model": LLM_MODEL}


@app.get("/dashboard")
async def dashboard():
    """Serve the Request Manager Dashboard UI"""
    html_path = Path(__file__).parent / "dashboard.html"
    if html_path.exists():
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("Dashboard UI not found", status_code=404)


@app.post("/sessions")
async def new_session(data: dict[str, Any]):
    """Create a new recording session"""
    domain = data.get("domain", "unknown")
    name = data.get("name")
    session_id = create_session(domain, name)
    return {"status": "ok", "session_id": session_id}


@app.get("/sessions")
async def list_sessions():
    """List recent recording sessions"""
    sessions = get_recent_sessions(limit=50)
    return {"status": "ok", "sessions": sessions}


@app.get("/sessions/{session_id}/requests")
async def get_session_data(session_id: str):
    """Get all requests for a given session"""
    requests = get_session_requests(session_id)
    return {
        "status": "ok",
        "requests": requests,
        "total": len(requests)
    }

@app.post("/sessions/{session_id}/ai-filter")
async def ai_filter_requests(session_id: str):
    """Uses LLM to classify and return junk/tracking request IDs"""
    requests = get_session_requests(session_id)
    if not requests:
        return {"junk_ids": []}

    # Extract only necessary info to save Tokens
    payload = []
    for r in requests:
        payload.append({
            "id": r["id"],
            "url": r["url"]
        })

    prompt = f"""You are an expert Network Analyst. Review the following list of web requests and identify which ones are tracking, analytics, ads, telemetry, or useless static junk (images, css, fonts) that should be deleted when reverse-engineering an API.
    
    Requests: {json.dumps(payload, ensure_ascii=False)}
    
    You MUST return ONLY a raw JSON array of integers representing the "id"s of the junk requests. Example: [12, 14, 55, 99]. DO NOT wrap in Markdown code blocks like ```json.
    """

    messages = [
        {"role": "system", "content": "You are a helpful assistant that strictly returns only JSON arrays of integers."},
        {"role": "user", "content": prompt}
    ]

    try:
        llm = get_llm()
        reply_text = await llm.chat(messages)
        # Parse the raw array
        reply_text = reply_text.strip()
        if reply_text.startswith("```json"):
            reply_text = reply_text[7:]
        if reply_text.startswith("```"):
            reply_text = reply_text[3:]
        if reply_text.endswith("```"):
            reply_text = reply_text[:-3]
        
        junk_ids = json.loads(reply_text.strip())
        if not isinstance(junk_ids, list):
            junk_ids = []
            
        return {"status": "ok", "junk_ids": junk_ids}
    except Exception as e:
        print(f"AI Filter Error: {e}")
        return {"status": "error", "message": str(e), "junk_ids": []}

@app.delete("/sessions/{session_id}")
async def remove_session(session_id: str):
    """Delete a recording session and all its child requests"""
    global requests_store
    delete_session(session_id)
    # Clear memory store in case it was showing this session
    requests_store = []
    return {"status": "ok", "deleted_session": session_id}

@app.delete("/requests/{request_id}")
async def remove_request(request_id: int):
    """Delete a single captured request"""
    global requests_store
    
    # 1. Delete from DB and get string ID
    req_str_id = delete_request(request_id)
    
    # 2. Sync in-memory store
    if req_str_id:
        requests_store = [req for req in requests_store if req.get("requestId") != req_str_id]
        
    return {"status": "ok", "deleted_request": request_id}

@app.post("/requests/bulk-delete")
async def bulk_remove_requests(data: dict[str, Any]):
    """Bulk delete multiple captured requests by ID"""
    global requests_store
    
    request_ids = data.get("request_ids", [])
    if request_ids:
        # 1. Delete from DB and get string IDs
        req_str_ids = delete_requests_bulk(request_ids)
        
        # 2. Sync in-memory store
        if req_str_ids:
            requests_store = [req for req in requests_store if req.get("requestId") not in req_str_ids]
            
    return {"status": "ok", "deleted_count": len(request_ids)}


@app.post("/requests")
async def add_requests(data: dict[str, Any]):
    """Add captured requests to the store (append)"""
    global requests_store

    requests_data = data.get("requests", [])
    session_id = data.get("session_id")
    
    if session_id and requests_data:
        save_requests(session_id, requests_data)

    if isinstance(requests_data, list):
        requests_store.extend(requests_data)

    return {"status": "ok", "count": len(requests_data)}


@app.put("/requests")
async def sync_requests(data: dict[str, Any]):
    """Replace all captured requests (sync from extension)"""
    global requests_store, capture_meta

    requests_data = data.get("requests", [])
    session_id = data.get("session_id")
    
    if session_id and requests_data:
        save_requests(session_id, requests_data)
        
    if isinstance(requests_data, list):
        requests_store = requests_data

    # Save metadata (cookies, tracked domains)
    meta = data.get("meta", {})
    if meta:
        capture_meta = meta
        if session_id:
            save_metadata(session_id, meta)

    return {"status": "ok", "count": len(requests_store)}


@app.get("/requests")
async def get_requests(limit: int = 100, session_id: str = None):
    """Get captured requests with metadata. If session_id provided, fetch from DB."""
    if session_id:
        requests = get_session_requests(session_id)
        meta = get_session_metadata(session_id)
        return {
            "requests": requests[-limit:],
            "total": len(requests),
            "meta": meta
        }
        
    if requests_store:
        return {
            "requests": requests_store[-limit:],
            "total": len(requests_store),
            "meta": capture_meta,
        }
        
    recent = get_recent_sessions(limit=1)
    if recent:
        latest_id = recent[0]["id"]
        requests = get_session_requests(latest_id)
        meta = get_session_metadata(latest_id)
        return {
            "requests": requests[-limit:],
            "total": len(requests),
            "meta": meta
        }
        
    return {"requests": [], "total": 0, "meta": {}}


@app.post("/clear")
async def clear_requests():
    """Clear all captured requests"""
    global requests_store
    count = len(requests_store)
    requests_store = []
    return {"status": "ok", "cleared": count}


# ─── P0 #2: Hybrid Smart Request Filtering ───
# Now powered by Brave's adblock-rust engine (EasyList + EasyPrivacy, 83K+ rules)
# + Rule-based patterns for instant classification
# See: vibeengine/smart_filter.py for full implementation


@app.post("/smart-filter")
async def smart_filter_requests(data: dict[str, Any] = None):
    """Hybrid smart filtering: Rule-based + Brave adblock engine (83K+ rules).
    Returns classified requests with category, confidence, and detection source."""
    source = requests_store
    if data and data.get("requests"):
        source = data["requests"]

    if not source:
        return {"error": "No requests to filter"}

    return classify_requests_batch(source)


@app.get("/requests/filtered")
async def get_filtered_requests(limit: int = 100):
    """Get only API-relevant requests (noise auto-removed by hybrid filter)."""
    source = requests_store
    if not source:
        recent = get_recent_sessions(limit=1)
        if recent:
            source = get_session_requests(recent[0]["id"])

    filtered = hybrid_filter_requests(source)
    return {
        "requests": filtered[-limit:],
        "total": len(filtered),
        "original_total": len(source),
        "noise_removed": len(source) - len(filtered),
        "meta": capture_meta,
    }


@app.get("/filter-engine/info")
async def filter_engine_info():
    """Get info about the loaded adblock filter engine."""
    return get_engine_info()


# ─── P0 #3: Cookie Bridge — Export cookies for scripts ───

@app.get("/cookies/export")
async def export_cookies(domain: str = None, format: str = "dict"):
    """Export captured cookies in script-ready format.
    
    Args:
        domain: Filter by domain (optional, returns all if omitted)
        format: Output format — dict, header_string, httpx, requests
    """
    all_cookies = capture_meta.get("capturedCookies", {})

    # Also extract cookies from request headers
    for req in requests_store:
        cookie_str = req.get("cookies", "")
        if not cookie_str:
            continue
        try:
            req_url = req.get("url", "")
            from urllib.parse import urlparse
            req_domain = urlparse(req_url).hostname or "unknown"
            if req_domain not in all_cookies:
                all_cookies[req_domain] = []
            # Parse cookie string into name=value pairs
            for part in cookie_str.split(";"):
                part = part.strip()
                if "=" in part:
                    name, value = part.split("=", 1)
                    # Avoid duplicates
                    existing_names = {c.get("name") for c in all_cookies.get(req_domain, [])}
                    if name.strip() not in existing_names:
                        all_cookies.setdefault(req_domain, []).append({
                            "name": name.strip(),
                            "value": value.strip(),
                            "domain": req_domain,
                        })
        except Exception:
            continue

    # Filter by domain if specified
    if domain:
        filtered = {}
        for d, cookies in all_cookies.items():
            if domain in d:
                filtered[d] = cookies
        all_cookies = filtered

    if not all_cookies:
        return {"error": "No cookies found", "hint": "Make sure to capture requests with cookies first"}

    # Build flat cookie dict (all domains merged)
    flat_cookies = {}
    for domain_key, cookie_list in all_cookies.items():
        for c in cookie_list:
            name = c.get("name", "")
            value = c.get("value", "")
            if name and value:
                flat_cookies[name] = value

    result = {
        "status": "ok",
        "domains": list(all_cookies.keys()),
        "total_cookies": len(flat_cookies),
        "cookies_by_domain": {d: len(cl) for d, cl in all_cookies.items()},
    }

    if format == "dict":
        result["cookies"] = flat_cookies
    elif format == "header_string":
        result["cookie_header"] = "; ".join(f"{k}={v}" for k, v in flat_cookies.items())
    elif format == "httpx":
        result["code"] = f"""import httpx\n\ncookies = {json.dumps(flat_cookies, indent=2, ensure_ascii=False)}\n\nclient = httpx.Client(cookies=cookies)\nresponse = client.get("https://{list(all_cookies.keys())[0] if all_cookies else 'example.com'}/")\nprint(response.status_code)"""
    elif format == "requests":
        result["code"] = f"""import requests\n\ncookies = {json.dumps(flat_cookies, indent=2, ensure_ascii=False)}\n\nresponse = requests.get("https://{list(all_cookies.keys())[0] if all_cookies else 'example.com'}/", cookies=cookies)\nprint(response.status_code)"""
    else:
        result["cookies"] = flat_cookies

    return result


# ─── P1 #4: Token Lifetime Detection ───
# Analyzes captured tokens/cookies for expiration, warns about short TTL,
# decodes JWT claims, parses Set-Cookie attributes.

import base64
import time as _time
import re as _re
from urllib.parse import urlparse as _urlparse
from datetime import datetime as _datetime, timezone as _timezone
from email.utils import parsedate_to_datetime as _parsedate

# Known patterns — BONUS HINTS only, NOT primary detection.
# If a token name matches, we add a human-readable note. Detection priority:
#   Layer 1 (highest): Set-Cookie Max-Age/Expires from actual response headers
#   Layer 2: Temporal diff across captured requests (value changed? → short-lived)
#   Layer 3: Heuristic analysis (JWT decode, entropy, embedded timestamps)
#   Layer 4 (lowest): Known pattern hints (this dict)
_KNOWN_TOKEN_HINTS = {
    "csrftoken": "CSRF token — typically session-bound",
    "csrf_token": "CSRF token — typically session-bound",
    "_ga": "Google Analytics — long-lived (2 years), safe to reuse",
    "_gid": "Google Analytics — short-lived (24 hours)",
}


def _decode_jwt_payload(token: str) -> dict | None:
    """Decode JWT payload without verification (for TTL analysis only)."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload_b64 = parts[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        decoded = base64.urlsafe_b64decode(payload_b64)
        return json.loads(decoded)
    except Exception:
        return None


def _parse_cookie_expiry(set_cookie_str: str) -> dict:
    """Layer 1: Parse Set-Cookie string to extract EXACT expiry info."""
    result = {
        "max_age": None,
        "expires": None,
        "expires_in_seconds": None,
        "is_session_cookie": True,
    }
    
    parts = set_cookie_str.split(";")
    for part in parts[1:]:
        part = part.strip().lower()
        if part.startswith("max-age="):
            try:
                result["max_age"] = int(part.split("=", 1)[1])
                result["expires_in_seconds"] = result["max_age"]
                result["is_session_cookie"] = False
            except ValueError:
                pass
        elif part.startswith("expires="):
            try:
                date_str = part.split("=", 1)[1].strip()
                exp_date = _parsedate(date_str)
                if exp_date:
                    now = _datetime.now(_timezone.utc)
                    delta = (exp_date - now).total_seconds()
                    result["expires"] = exp_date.isoformat()
                    result["expires_in_seconds"] = max(0, int(delta))
                    result["is_session_cookie"] = False
            except Exception:
                pass
    
    return result


def _calc_entropy(s: str) -> float:
    """Calculate Shannon entropy of a string (higher = more random/dynamic)."""
    import math
    if not s:
        return 0.0
    freq = {}
    for c in s:
        freq[c] = freq.get(c, 0) + 1
    length = len(s)
    return -sum((count / length) * math.log2(count / length) for count in freq.values())


def _extract_embedded_timestamp(value: str) -> int | None:
    """Detect if value contains an embedded Unix timestamp (common in dynamic tokens)."""
    # Check for raw Unix timestamps (10 or 13 digits)
    # Use lookaround instead of \b — works with underscore/dash delimiters
    for match in _re.finditer(r'(?<!\d)(\d{10})(?!\d)', value):
        ts = int(match.group(1))
        now = int(_time.time())
        # Valid if within 10 years from now (past or future)
        if abs(ts - now) < 315360000:
            return ts
    for match in _re.finditer(r'(?<!\d)(\d{13})(?!\d)', value):
        ts = int(match.group(1)) // 1000
        now = int(_time.time())
        if abs(ts - now) < 315360000:
            return ts
    
    # Check hex-encoded timestamps at start/end (e.g., "67c..." = hex timestamp)
    if len(value) >= 8 and all(c in "0123456789abcdef" for c in value[:8].lower()):
        try:
            ts = int(value[:8], 16)
            now = int(_time.time())
            if abs(ts - now) < 315360000:
                return ts
        except ValueError:
            pass
    
    return None


def _build_temporal_diff(requests_list: list) -> dict:
    """Layer 2: Compare cookie values across requests to detect rotating tokens.
    
    Returns dict: {domain: {cookie_name: {"values": set, "is_rotating": bool, "change_count": int}}}
    """
    tracking: dict[str, dict[str, list]] = {}  # domain -> {name -> [values in order]}
    
    for req in requests_list:
        cookie_str = req.get("cookies", "")
        if not cookie_str:
            continue
        req_url = req.get("url", "")
        try:
            domain = _urlparse(req_url).hostname or "unknown"
        except Exception:
            continue
        
        if domain not in tracking:
            tracking[domain] = {}
        
        for part in cookie_str.split(";"):
            part = part.strip()
            if "=" in part:
                name, value = part.split("=", 1)
                name = name.strip()
                value = value.strip()
                if not name or not value:
                    continue
                if name not in tracking[domain]:
                    tracking[domain][name] = []
                tracking[domain][name].append(value)
    
    result = {}
    for domain, cookies in tracking.items():
        result[domain] = {}
        for name, values in cookies.items():
            unique_values = set(values)
            total_seen = len(values)
            change_count = total_seen - 1 if len(unique_values) > 1 else 0
            
            result[domain][name] = {
                "unique_values": len(unique_values),
                "total_seen": total_seen,
                "is_rotating": len(unique_values) > 1 and total_seen >= 2,
                "change_count": change_count,
                "stability_ratio": 1.0 / len(unique_values) if unique_values else 1.0,
                # If value changes every request, it's per-request dynamic
                "is_per_request": len(unique_values) == total_seen and total_seen >= 3,
            }
    
    return result


def _build_set_cookie_ttl_map(requests_list: list) -> dict:
    """Layer 1: Build map of exact TTLs from Set-Cookie response headers.
    
    Returns dict: {cookie_name: {"ttl_seconds": int, "source_url": str, ...}}
    """
    ttl_map = {}
    
    for req in requests_list:
        for sc in req.get("setCookies", []):
            if "=" not in sc:
                continue
            cookie_name = sc.split("=", 1)[0].strip()
            expiry = _parse_cookie_expiry(sc)
            
            if expiry["expires_in_seconds"] is not None or not expiry["is_session_cookie"]:
                ttl_map[cookie_name] = {
                    **expiry,
                    "source_url": req.get("url", "")[:100],
                }
    
    return ttl_map


def _analyze_token_value(
    name: str,
    value: str,
    set_cookie_ttl: dict | None = None,
    temporal_diff: dict | None = None,
    domain: str = "",
) -> dict:
    """Analyze a single token/cookie using the 4-layer dynamic system.
    
    Priority:
        Layer 1: Set-Cookie Max-Age/Expires (exact TTL from server)
        Layer 2: Temporal diff (value rotation across requests)
        Layer 3: Heuristic (JWT, entropy, embedded timestamps, structure)
        Layer 4: Known hints (bonus only)
    """
    analysis = {
        "name": name,
        "value_preview": value[:20] + "..." if len(value) > 20 else value,
        "length": len(value),
        "type": "unknown",
        "ttl_warning": None,
        "ttl_seconds": None,
        "jwt_info": None,
        "reusable": True,
        "detection_layer": None,
        "confidence": "low",
    }
    
    # ── Layer 1: Exact TTL from Set-Cookie ──
    if set_cookie_ttl and name in set_cookie_ttl:
        sc_info = set_cookie_ttl[name]
        ttl = sc_info.get("expires_in_seconds")
        if ttl is not None:
            analysis["ttl_seconds"] = ttl
            analysis["detection_layer"] = "set-cookie"
            analysis["confidence"] = "high"
            
            if ttl <= 0:
                analysis["type"] = "expired_by_server"
                analysis["ttl_warning"] = f"Server set expired (TTL={ttl}s) — deletion cookie"
                analysis["reusable"] = False
            elif ttl < 300:  # < 5 min
                analysis["type"] = "very_short_lived"
                analysis["ttl_warning"] = f"Server TTL: {ttl}s ({ttl//60}min) — very short, likely anti-bot"
                analysis["reusable"] = False
            elif ttl < 1800:  # < 30 min
                analysis["type"] = "short_lived"
                analysis["ttl_warning"] = f"Server TTL: {ttl}s ({ttl//60}min) — short-lived"
            elif ttl < 86400:  # < 1 day
                analysis["type"] = "medium_lived"
                analysis["ttl_warning"] = f"Server TTL: {ttl//3600}h — medium lifetime"
            else:
                analysis["type"] = "long_lived"
                # No warning for long-lived tokens
            
            # Early return — Layer 1 is definitive
            return analysis
    
    # ── Layer 2: Temporal diff across requests ──
    if temporal_diff:
        domain_diff = temporal_diff.get(domain, {})
        if name in domain_diff:
            diff = domain_diff[name]
            
            if diff["is_per_request"]:
                analysis["type"] = "per_request_dynamic"
                analysis["ttl_warning"] = (
                    f"Value changes every request ({diff['unique_values']} unique in "
                    f"{diff['total_seen']} requests) — dynamic signature, cannot reuse"
                )
                analysis["reusable"] = False
                analysis["detection_layer"] = "temporal_diff"
                analysis["confidence"] = "high"
                return analysis
            
            elif diff["is_rotating"]:
                analysis["type"] = "rotating"
                analysis["ttl_warning"] = (
                    f"Value rotated {diff['change_count']}x across {diff['total_seen']} requests — "
                    f"short-lived, re-capture frequently"
                )
                analysis["reusable"] = True  # Can reuse temporarily
                analysis["detection_layer"] = "temporal_diff"
                analysis["confidence"] = "medium"
                # Don't return — let lower layers enrich
    
    # ── Layer 3: Heuristic analysis ──
    
    # 3a: JWT detection (universal, works for any website)
    jwt_payload = _decode_jwt_payload(value)
    if jwt_payload:
        analysis["type"] = "jwt"
        analysis["detection_layer"] = analysis["detection_layer"] or "heuristic_jwt"
        analysis["confidence"] = "high"
        jwt_info = {"claims": list(jwt_payload.keys())}
        
        if "exp" in jwt_payload:
            exp_ts = jwt_payload["exp"]
            now_ts = _time.time()
            remaining = exp_ts - now_ts
            jwt_info["expires_at"] = _datetime.fromtimestamp(exp_ts, _timezone.utc).isoformat()
            jwt_info["remaining_seconds"] = int(remaining)
            analysis["ttl_seconds"] = int(remaining)
            
            if remaining <= 0:
                jwt_info["status"] = "⛔ EXPIRED"
                analysis["ttl_warning"] = f"JWT expired {int(-remaining)}s ago!"
                analysis["reusable"] = False
            elif remaining < 300:
                jwt_info["status"] = "🔴 EXPIRING SOON"
                analysis["ttl_warning"] = f"JWT expires in {int(remaining)}s — capture fresh token!"
            elif remaining < 3600:
                jwt_info["status"] = "🟡 SHORT-LIVED"
                analysis["ttl_warning"] = f"JWT expires in {int(remaining/60)}min"
            else:
                jwt_info["status"] = "🟢 OK"
                
        if "iat" in jwt_payload:
            jwt_info["issued_at"] = _datetime.fromtimestamp(
                jwt_payload["iat"], _timezone.utc
            ).isoformat()
        if "sub" in jwt_payload:
            jwt_info["subject"] = str(jwt_payload["sub"])[:30]
            
        analysis["jwt_info"] = jwt_info
        return analysis
    
    # 3b: Embedded timestamp detection
    embedded_ts = _extract_embedded_timestamp(value)
    if embedded_ts:
        remaining = embedded_ts - _time.time()
        analysis["detection_layer"] = analysis["detection_layer"] or "heuristic_timestamp"
        analysis["confidence"] = "medium"
        
        if remaining > 0:
            analysis["type"] = "timestamp_based"
            analysis["ttl_seconds"] = int(remaining)
            if remaining < 300:
                analysis["ttl_warning"] = f"Embedded timestamp expires in {int(remaining)}s"
            elif remaining < 3600:
                analysis["ttl_warning"] = f"Embedded timestamp expires in {int(remaining/60)}min"
        elif remaining < 0 and remaining > -86400:  # expired within last day
            analysis["type"] = "timestamp_based"
            analysis["ttl_warning"] = f"Embedded timestamp expired {int(-remaining)}s ago"
            analysis["reusable"] = False
    
    # 3c: Entropy analysis (high entropy = likely dynamic/signature)
    if analysis["type"] == "unknown" and len(value) >= 20:
        entropy = _calc_entropy(value)
        analysis["entropy"] = round(entropy, 2)
        
        if entropy > 4.5 and len(value) > 50:
            # High entropy + long value = likely dynamic signature
            analysis["type"] = "high_entropy_token"
            analysis["detection_layer"] = analysis["detection_layer"] or "heuristic_entropy"
            analysis["confidence"] = "low"
            # Don't warn — high entropy alone doesn't mean short-lived
        
        elif entropy < 2.0 and len(value) > 20:
            # Low entropy = likely static/identifier
            analysis["type"] = "static_identifier"
            analysis["detection_layer"] = analysis["detection_layer"] or "heuristic_entropy"
    
    # 3d: Structure patterns
    if analysis["type"] == "unknown":
        if len(value) > 30 and all(c in "0123456789abcdef" for c in value.lower()):
            analysis["type"] = "hex_token"
        elif len(value) > 100 and "=" in value[-3:]:
            analysis["type"] = "base64_token"
        elif len(value) > 100:
            analysis["type"] = "long_token"
        elif _re.match(r'^\d{10,13}$', value):
            analysis["type"] = "raw_timestamp"
    
    # ── Layer 4: Known hints (bonus, lowest priority) ──
    if not analysis["ttl_warning"]:
        name_lower = name.lower().replace("-", "_")
        for pattern, hint in _KNOWN_TOKEN_HINTS.items():
            if pattern in name_lower:
                analysis["known_hint"] = hint
                analysis["detection_layer"] = analysis["detection_layer"] or "known_hint"
                break
    
    if not analysis["detection_layer"]:
        analysis["detection_layer"] = "none"
        analysis["confidence"] = "unknown"
    
    return analysis


# Auto-refresh state
_auto_refresh_tasks: dict[str, dict] = {}
_refresh_running = False


@app.get("/tokens/analyze")
async def analyze_tokens(domain: str = None):
    """Analyze captured tokens/cookies for expiration and TTL warnings.
    
    P1 #4: Token Lifetime Detection — 4-Layer Dynamic System
    Layer 1: Set-Cookie Max-Age/Expires (exact TTL from server response)
    Layer 2: Temporal diff (compare cookie values across requests)
    Layer 3: Heuristic (JWT decode, entropy, embedded timestamps)
    Layer 4: Known hints (bonus only, minimal hardcoding)
    """
    all_cookies = dict(capture_meta.get("capturedCookies", {}))
    
    # Also extract from requests
    for req in requests_store:
        cookie_str = req.get("cookies", "")
        if not cookie_str:
            continue
        try:
            req_url = req.get("url", "")
            req_domain = _urlparse(req_url).hostname or "unknown"
            if domain and domain not in req_domain:
                continue
            for part in cookie_str.split(";"):
                part = part.strip()
                if "=" in part:
                    name, value = part.split("=", 1)
                    existing = {c.get("name") for c in all_cookies.get(req_domain, [])}
                    if name.strip() not in existing:
                        all_cookies.setdefault(req_domain, []).append({
                            "name": name.strip(), "value": value.strip(), "domain": req_domain
                        })
        except Exception:
            continue
    
    # Filter by domain
    if domain:
        all_cookies = {d: cl for d, cl in all_cookies.items() if domain in d}
    
    if not all_cookies:
        return {"error": "No tokens/cookies found", "hint": "Capture requests first"}
    
    # ── Build dynamic analysis context from captured data ──
    # Layer 1: Exact TTLs from Set-Cookie response headers
    set_cookie_ttl = _build_set_cookie_ttl_map(requests_store)
    
    # Layer 2: Temporal diff — detect rotating/dynamic tokens
    temporal_diff = _build_temporal_diff(requests_store)
    
    # Set-Cookie analysis for output
    set_cookie_analysis = []
    for req in requests_store:
        for sc in req.get("setCookies", []):
            expiry = _parse_cookie_expiry(sc)
            cookie_name = sc.split("=", 1)[0].strip() if "=" in sc else "unknown"
            set_cookie_analysis.append({
                "cookie_name": cookie_name,
                "source_url": req.get("url", "")[:80],
                **expiry,
            })
    
    # Analyze each token using all 4 layers
    domain_results = {}
    warnings = []
    expired_count = 0
    short_lived_count = 0
    dynamic_count = 0
    reusable_count = 0
    total_count = 0
    layer_stats = {"set-cookie": 0, "temporal_diff": 0, "heuristic_jwt": 0,
                   "heuristic_timestamp": 0, "heuristic_entropy": 0, "known_hint": 0, "none": 0}
    
    for d, cookie_list in all_cookies.items():
        token_analyses = []
        for cookie in cookie_list:
            name = cookie.get("name", "")
            value = cookie.get("value", "")
            if not name or not value:
                continue
            total_count += 1
            analysis = _analyze_token_value(
                name, value,
                set_cookie_ttl=set_cookie_ttl,
                temporal_diff=temporal_diff,
                domain=d,
            )
            token_analyses.append(analysis)
            
            # Stats
            layer = analysis.get("detection_layer", "none")
            layer_stats[layer] = layer_stats.get(layer, 0) + 1
            
            if analysis.get("reusable"):
                reusable_count += 1
            if analysis.get("type") in ("per_request_dynamic",):
                dynamic_count += 1
            if analysis.get("ttl_warning"):
                warn_text = analysis["ttl_warning"]
                if "expired" in warn_text.lower() or "EXPIRED" in warn_text:
                    expired_count += 1
                    warnings.append(f"⛔ [{d}] {name}: {warn_text}")
                elif "EXPIRING" in warn_text or "cannot reuse" in warn_text:
                    short_lived_count += 1
                    warnings.append(f"🔴 [{d}] {name}: {warn_text}")
                elif "short" in warn_text.lower() or "very short" in warn_text.lower():
                    short_lived_count += 1
                    warnings.append(f"🟡 [{d}] {name}: {warn_text}")
                else:
                    warnings.append(f"🟡 [{d}] {name}: {warn_text}")
        
        domain_results[d] = token_analyses
    
    # Temporal diff summary for output
    temporal_summary = {}
    for d, cookies in temporal_diff.items():
        rotating = {n: info for n, info in cookies.items() if info["is_rotating"]}
        if rotating:
            temporal_summary[d] = {
                name: {
                    "unique_values": info["unique_values"],
                    "total_seen": info["total_seen"],
                    "is_per_request": info["is_per_request"],
                }
                for name, info in rotating.items()
            }
    
    return {
        "status": "ok",
        "summary": {
            "total_tokens": total_count,
            "expired": expired_count,
            "short_lived": short_lived_count,
            "dynamic_per_request": dynamic_count,
            "reusable": reusable_count,
            "domains_analyzed": len(domain_results),
        },
        "detection_layers_used": {k: v for k, v in layer_stats.items() if v > 0},
        "warnings": warnings,
        "tokens_by_domain": domain_results,
        "set_cookie_expiry": set_cookie_analysis,
        "rotating_tokens": temporal_summary,
        "recommendation": (
            "🔴 Some tokens are expired or short-lived! Use export_cookies to get fresh tokens from browser, "
            "or enable auto-refresh to keep tokens updated."
            if expired_count > 0 or short_lived_count > 0
            else (
                "🟠 Dynamic per-request tokens detected. These cannot be reused — "
                "you must capture fresh tokens for each script run."
                if dynamic_count > 0
                else "🟢 All tokens appear healthy. Monitor with periodic checks."
            )
        ),
    }


@app.post("/tokens/auto-refresh")
async def setup_auto_refresh(data: dict[str, Any]):
    """Setup auto-refresh for token/cookie monitoring.
    
    P1 #5: Auto-Refresh Mechanism
    When enabled, VibeLens will:
    1. Periodically check token expiration status
    2. Re-export cookies from the active browser session
    3. Log warnings when tokens are about to expire
    4. Optionally trigger a callback URL when refresh is needed
    
    Args (in JSON body):
        action: "start" | "stop" | "status"
        domain: Domain to monitor (optional, all if omitted)
        interval_seconds: Check interval (default: 60)
        callback_url: URL to notify when tokens expire (optional)
    """
    global _auto_refresh_tasks, _refresh_running
    
    action = data.get("action", "status")
    domain = data.get("domain", "*")
    interval = data.get("interval_seconds", 60)
    callback_url = data.get("callback_url")
    
    if action == "start":
        task_id = f"refresh_{domain}_{int(_time.time())}"
        _auto_refresh_tasks[task_id] = {
            "id": task_id,
            "domain": domain,
            "interval_seconds": interval,
            "callback_url": callback_url,
            "status": "active",
            "created_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "last_check": None,
            "check_count": 0,
            "warnings": [],
            "expired_tokens": [],
        }
        
        # Start background checker if not running
        if not _refresh_running:
            import asyncio
            asyncio.create_task(_token_refresh_worker())
            _refresh_running = True
        
        return {
            "status": "ok",
            "message": f"Auto-refresh started for domain '{domain}' every {interval}s",
            "task_id": task_id,
        }
    
    elif action == "stop":
        task_id = data.get("task_id")
        if task_id and task_id in _auto_refresh_tasks:
            _auto_refresh_tasks[task_id]["status"] = "stopped"
            return {"status": "ok", "message": f"Stopped task {task_id}"}
        elif not task_id:
            # Stop all
            for t in _auto_refresh_tasks.values():
                t["status"] = "stopped"
            return {"status": "ok", "message": "All auto-refresh tasks stopped"}
        else:
            return {"error": f"Task {task_id} not found"}
    
    else:  # status
        return {
            "status": "ok",
            "running": _refresh_running,
            "tasks": list(_auto_refresh_tasks.values()),
            "active_count": sum(1 for t in _auto_refresh_tasks.values() if t["status"] == "active"),
        }


@app.get("/tokens/refresh-status")
async def get_refresh_status():
    """Get current auto-refresh status and recent warnings."""
    return {
        "running": _refresh_running,
        "tasks": list(_auto_refresh_tasks.values()),
        "active_count": sum(1 for t in _auto_refresh_tasks.values() if t["status"] == "active"),
    }


async def _token_refresh_worker():
    """Background worker that periodically checks token health."""
    global _refresh_running
    import asyncio
    
    logger = logging.getLogger("vibelens.token-refresh")
    logger.info("🔄 Token auto-refresh worker started")
    
    try:
        while True:
            active_tasks = [t for t in _auto_refresh_tasks.values() if t["status"] == "active"]
            if not active_tasks:
                logger.info("No active refresh tasks, worker stopping")
                break
            
            for task in active_tasks:
                now = _time.time()
                last = task.get("_last_check_ts", 0)
                
                if now - last < task["interval_seconds"]:
                    continue
                
                task["_last_check_ts"] = now
                task["last_check"] = _time.strftime("%Y-%m-%dT%H:%M:%SZ")
                task["check_count"] += 1
                
                # Analyze tokens with dynamic context
                domain_filter = task["domain"] if task["domain"] != "*" else None
                all_cookies = dict(capture_meta.get("capturedCookies", {}))
                
                # Build dynamic context
                sc_ttl = _build_set_cookie_ttl_map(requests_store)
                t_diff = _build_temporal_diff(requests_store)
                
                # Quick scan for expired tokens
                new_warnings = []
                expired_tokens = []
                
                for d, cookie_list in all_cookies.items():
                    if domain_filter and domain_filter not in d:
                        continue
                    for cookie in cookie_list:
                        name = cookie.get("name", "")
                        value = cookie.get("value", "")
                        if not name or not value:
                            continue
                        
                        analysis = _analyze_token_value(
                            name, value,
                            set_cookie_ttl=sc_ttl,
                            temporal_diff=t_diff,
                            domain=d,
                        )
                        if analysis.get("ttl_warning"):
                            warning_msg = f"[{d}] {name}: {analysis['ttl_warning']}"
                            new_warnings.append(warning_msg)
                            
                            if not analysis.get("reusable"):
                                expired_tokens.append(name)
                
                task["warnings"] = new_warnings[-20:]  # Keep last 20
                task["expired_tokens"] = expired_tokens
                
                if expired_tokens:
                    logger.warning(f"⚠️ Expired tokens detected: {expired_tokens}")
                    
                    # Trigger callback if configured
                    if task.get("callback_url"):
                        try:
                            import httpx as _httpx
                            async with _httpx.AsyncClient(timeout=10) as client:
                                await client.post(task["callback_url"], json={
                                    "event": "tokens_expired",
                                    "domain": task["domain"],
                                    "expired_tokens": expired_tokens,
                                    "warnings": new_warnings,
                                    "timestamp": task["last_check"],
                                })
                        except Exception as e:
                            logger.error(f"Callback failed: {e}")
            
            await asyncio.sleep(5)  # Check every 5s for task scheduling
    
    except asyncio.CancelledError:
        logger.info("Token refresh worker cancelled")
    except Exception as e:
        logger.error(f"Token refresh worker error: {e}")
    finally:
        _refresh_running = False


@app.post("/analyze")
async def analyze_requests(data: AnalyzeRequest):
    """Analyze requests with AI"""
    requests = data.requests if data.requests else requests_store

    if not requests:
        return {"analysis": "No requests to analyze"}

    context = build_request_context(requests)

    prompt = data.prompt or """Analyze these API requests and provide:
1. API endpoints and their purposes
2. Authentication methods used
3. Request/response patterns
4. Potential improvements or issues
5. Suggested code to replicate these calls"""

    messages = [
        {"role": "system", "content": "You are an API expert. Analyze network requests and provide insights."},
        {"role": "user", "content": f"{prompt}\n\n{context}"}
    ]

    try:
        llm = get_llm()
        analysis = await llm.chat(messages)

        return {
            "analysis": analysis,
            "request_count": len(requests),
            "provider": LLM_PROVIDER,
            "model": LLM_MODEL,
        }
    except Exception as e:
        return {"error": str(e)}


@app.post("/generate")
async def generate_code(data: dict[str, Any]):
    """Generate code from captured requests"""
    requests = data.get("requests", requests_store)
    language = data.get("language", "python")

    if not requests:
        return {"code": "# No requests captured"}

    api_requests = [r for r in requests if "/api/" in r.get("url", "")]

    context = build_request_context(api_requests)

    if language == "curl":
        prompt = "Convert these API calls to curl commands:"
    elif language == "javascript":
        prompt = "Convert these API calls to JavaScript fetch/axios code:"
    else:
        prompt = "Convert these API calls to Python requests code:"

    messages = [
        {"role": "system", "content": "You are a code generator. Convert API calls to executable code."},
        {"role": "user", "content": f"{prompt}\n\n{context}"}
    ]

    try:
        llm = get_llm()
        code = await llm.chat(messages)

        return {
            "code": code,
            "language": language,
            "request_count": len(api_requests),
            "provider": LLM_PROVIDER,
        }
    except Exception as e:
        return {"error": str(e)}


@app.post("/explain")
async def explain_request(data: dict[str, Any]):
    """Explain a specific request in detail"""
    request = data.get("request", {})

    if not request:
        return {"error": "No request provided"}

    prompt = f"""Explain this API request in detail:
- What does it do?
- What headers are needed?
- What's the expected response?
- How to replicate it?

Request:
Method: {request.get('method', 'GET')}
URL: {request.get('url', '')}
Headers: {json.dumps(request.get('headers', {}), indent=2)}
Body: {request.get('postData', 'N/A')}"""

    messages = [
        {"role": "system", "content": "You are an API expert. Explain requests in detail."},
        {"role": "user", "content": prompt}
    ]

    try:
        llm = get_llm()
        explanation = await llm.chat(messages)
        return {"explanation": explanation}
    except Exception as e:
        return {"error": str(e)}


# ─── Smart Response Body Trimmer ───
# Handles HTML, JSON, XML intelligently instead of dumb [:2000] cuts

def smart_trim_body(body: str, max_chars: int = 3000, context: str = "ai") -> str:
    """Intelligently trim response body based on content type.
    
    Args:
        body: Raw response body string
        max_chars: Max chars to return (3000 for AI context, 8000 for detail view)
        context: 'ai' for analysis context, 'detail' for get_request_detail
    """
    if not body or len(body) <= max_chars:
        return body

    body_lower = body.strip()[:200].lower()

    # ── JSON: Parse and extract schema + sample ──
    if body_lower.startswith('{') or body_lower.startswith('['):
        return _trim_json(body, max_chars)

    # ── HTML: Extract meaningful content only ──
    if '<html' in body_lower or '<!doctype' in body_lower or '<head' in body_lower:
        return _trim_html(body, max_chars)

    # ── XML: Trim at tag boundary ──
    if body_lower.startswith('<?xml') or '</' in body_lower[:500]:
        return _trim_xml(body, max_chars)

    # ── Plain text: Trim at line boundary ──
    lines = body.split('\n')
    result = []
    char_count = 0
    for line in lines:
        if char_count + len(line) > max_chars:
            break
        result.append(line)
        char_count += len(line) + 1
    trimmed = '\n'.join(result)
    if len(trimmed) < len(body):
        trimmed += f'\n... [text truncated, {len(body):,} chars total]'
    return trimmed


def _trim_json(body: str, max_chars: int) -> str:
    """Smart JSON trimming: preserve structure, sample data."""
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        # Invalid JSON — fall back to boundary-aware cut
        cut_point = body.rfind('},', 0, max_chars)
        if cut_point == -1:
            cut_point = body.rfind(',', 0, max_chars)
        if cut_point == -1:
            cut_point = max_chars
        return body[:cut_point + 1] + f'\n... [JSON truncated, {len(body):,} chars total]'

    def _summarize(obj, depth=0, max_depth=3):
        """Recursively summarize JSON structure."""
        if depth >= max_depth:
            if isinstance(obj, dict):
                return {"...": f"({len(obj)} keys)"}
            if isinstance(obj, list):
                return [f"... ({len(obj)} items)"]
            return obj

        if isinstance(obj, dict):
            result = {}
            for i, (k, v) in enumerate(obj.items()):
                if i >= 10:  # Max 10 keys per level
                    result[f"... +{len(obj) - 10} more keys"] = "..."
                    break
                result[k] = _summarize(v, depth + 1, max_depth)
            return result

        if isinstance(obj, list):
            if not obj:
                return []
            # Show first 3 items + count
            sample = [_summarize(item, depth + 1, max_depth) for item in obj[:3]]
            if len(obj) > 3:
                sample.append(f"... +{len(obj) - 3} more items (total: {len(obj)})")
            return sample

        # Truncate long strings
        if isinstance(obj, str) and len(obj) > 200:
            return obj[:200] + '...'

        return obj

    summarized = _summarize(data)
    result = json.dumps(summarized, indent=2, ensure_ascii=False)

    # If summary is still too long, cut it
    if len(result) > max_chars:
        cut_point = result.rfind('\n', 0, max_chars)
        if cut_point == -1:
            cut_point = max_chars
        result = result[:cut_point] + f'\n... [JSON summary truncated]'

    if len(body) > max_chars:
        result += f'\n[Original: {len(body):,} chars]'

    return result


def _trim_html(body: str, max_chars: int) -> str:
    """Smart HTML trimming using trafilatura + selectolax.
    
    Pipeline:
    1. trafilatura: Extract main text content + metadata (F1=0.937)
    2. selectolax: Extract forms, JSON-LD, inline data (24x faster than BS4)
    3. Regex fallback: Only if libraries fail
    """
    parts = []

    # ── Layer 1: trafilatura — main content extraction ──
    try:
        import trafilatura

        # Extract main text with metadata
        extracted = trafilatura.extract(
            body,
            include_comments=False,
            include_tables=True,
            include_links=True,
            include_images=False,
            favor_precision=True,  # Less noise, more relevant
            output_format='txt',
        )
        if extracted and len(extracted.strip()) > 30:
            # Trim to fit budget
            text_budget = max_chars * 2 // 3  # 2/3 of budget for main text
            if len(extracted) > text_budget:
                extracted = extracted[:text_budget] + '...'
            parts.append(f"Content: {extracted}")

        # Extract metadata separately
        metadata = trafilatura.extract_metadata(body)
        if metadata:
            if metadata.title:
                parts.insert(0, f"Title: {metadata.title}")
            if metadata.description:
                parts.insert(1, f"Description: {metadata.description}")
            if metadata.author:
                parts.append(f"Author: {metadata.author}")
            if metadata.date:
                parts.append(f"Date: {metadata.date}")

    except Exception as e:
        # trafilatura failed — use regex fallback for title
        import re
        title_match = re.search(r'<title[^>]*>(.*?)</title>', body, re.IGNORECASE | re.DOTALL)
        if title_match:
            parts.append(f"Title: {title_match.group(1).strip()}")

    # ── Layer 2: selectolax — structured data extraction ──
    try:
        from selectolax.parser import HTMLParser

        tree = HTMLParser(body)

        # JSON-LD structured data (product info, breadcrumbs, etc.)
        for script in tree.css('script[type="application/ld+json"]'):
            try:
                ld_text = script.text(strip=True)
                if ld_text:
                    parsed = json.loads(ld_text)
                    ld_str = json.dumps(parsed, ensure_ascii=False)
                    if len(ld_str) > 600:
                        ld_str = _trim_json(ld_str, 600)
                    parts.append(f"StructuredData: {ld_str}")
            except Exception:
                pass

        # Inline SPA data (Shopee, TikTok, Next.js)
        for script in tree.css('script'):
            text = script.text(strip=True) or ""
            for pattern in ['__INITIAL_STATE__', '__NEXT_DATA__', '__PRELOADED_STATE__', '__DATA__']:
                if pattern in text:
                    # Extract JSON after the assignment
                    eq_pos = text.find('=', text.find(pattern))
                    if eq_pos != -1:
                        json_part = text[eq_pos + 1:].strip().rstrip(';')
                        if json_part:
                            trimmed = _trim_json(json_part, max_chars // 3)
                            parts.append(f"InlineData ({pattern}): {trimmed}")
                    break

        # Forms (login, search, cart — important for API analysis)
        for form in tree.css('form'):
            action = form.attributes.get('action', '?')
            method = form.attributes.get('method', 'GET')
            fields = []
            for inp in form.css('input[name], select[name], textarea[name]'):
                name = inp.attributes.get('name', '')
                input_type = inp.attributes.get('type', 'text')
                if name:
                    fields.append(f"{name}({input_type})")
            if fields:
                parts.append(f"Form: {method.upper()} {action} → fields={fields}")

        # Meta description (if not already captured by trafilatura)
        if not any('Description:' in p for p in parts):
            desc = tree.css_first('meta[name="description"]')
            if desc:
                parts.append(f"Description: {desc.attributes.get('content', '')}")

    except ImportError:
        # selectolax not available — regex fallback for forms
        import re
        form_matches = re.findall(r'<form[^>]*>(.*?)</form>', body, re.IGNORECASE | re.DOTALL)
        for form in form_matches[:3]:
            inputs = re.findall(r'<input[^>]*name=["\']([^"\']*)["\']', form)
            if inputs:
                parts.append(f"Form: fields={inputs}")
    except Exception:
        pass

    # ── Assemble result ──
    if not parts:
        # Emergency fallback: raw text extraction
        import re
        text = re.sub(r'<script[^>]*>.*?</script>', '', body, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        if text:
            parts.append(f"Text: {text[:max_chars]}")

    summary = '\n'.join(parts)
    if len(summary) > max_chars:
        summary = summary[:max_chars]
    
    stats = f"\n[HTML: {len(body):,} chars → extracted {len(summary):,} chars]"
    return summary + stats


def _trim_xml(body: str, max_chars: int) -> str:
    """Trim XML at tag boundary, using selectolax for fast parsing."""
    try:
        from selectolax.parser import HTMLParser
        tree = HTMLParser(body)
        text = tree.text(strip=True) or ""
        if text and len(text) > 50:
            if len(text) > max_chars:
                text = text[:max_chars]
            return f"{text}\n[XML: {len(body):,} chars]"
    except Exception:
        pass

    # Fallback: find last closing tag before limit
    cut = body.rfind('>', 0, max_chars)
    if cut == -1:
        cut = max_chars
    return body[:cut + 1] + f'\n... [XML truncated, {len(body):,} chars total]'


def build_request_context(requests: list[dict[str, Any]], include_response_body: bool = True) -> str:
    """Build context string from requests (with masking applied).
    P0 Fix: Now includes response body for AI analysis."""
    lines = []

    for i, req in enumerate(requests[:50]):
        masked_req = mask_request(req)
        lines.append(f"\n--- Request {i + 1} ---")
        lines.append(f"Method: {masked_req.get('method', 'GET')}")
        lines.append(f"URL: {masked_req.get('url', '')}")

        if masked_req.get('headers'):
            lines.append(f"Headers: {json.dumps(masked_req['headers'], indent=2)}")

        if masked_req.get('postData'):
            lines.append(f"Body: {masked_req['postData']}")

        if masked_req.get('status'):
            lines.append(f"Status: {masked_req['status']}")

        # P0 #1: Include response body — smart trimmed based on content type
        if include_response_body:
            resp_body = masked_req.get('responseBody') or masked_req.get('response_body')
            if resp_body and resp_body not in ('null', 'None', ''):
                if not str(resp_body).startswith('[SKIPPED'):
                    trimmed = smart_trim_body(str(resp_body), max_chars=3000, context='ai')
                    lines.append(f"Response: {trimmed}")

    return "\n".join(lines)

# ─── Masking Config Endpoints ───
@app.get("/masking")
async def get_masking_config():
    """Get current masking configuration"""
    return {
        "enabled": MASKING_ENABLED,
        "sensitive_headers": SENSITIVE_HEADERS,
        "sensitive_body_keys": SENSITIVE_BODY_KEYS,
    }


@app.post("/masking")
async def update_masking_config(data: dict[str, Any]):
    """Update masking config (enable/disable, add/remove sensitive keys)"""
    global MASKING_ENABLED, SENSITIVE_HEADERS, SENSITIVE_BODY_KEYS

    if "enabled" in data:
        MASKING_ENABLED = bool(data["enabled"])
    if "add_headers" in data:
        SENSITIVE_HEADERS.extend([h.lower() for h in data["add_headers"]])
    if "add_body_keys" in data:
        SENSITIVE_BODY_KEYS.extend([k.lower() for k in data["add_body_keys"]])
    if "remove_headers" in data:
        SENSITIVE_HEADERS[:] = [h for h in SENSITIVE_HEADERS if h not in data["remove_headers"]]
    if "remove_body_keys" in data:
        SENSITIVE_BODY_KEYS[:] = [k for k in SENSITIVE_BODY_KEYS if k not in data["remove_body_keys"]]

    return {"status": "ok", "enabled": MASKING_ENABLED}


# ─── Vibe Blueprints Endpoints ───
@app.post("/blueprints")
async def create_blueprint(data: dict[str, Any]):
    """Create a Vibe Blueprint from captured requests"""
    import time

    name = data.get("name", "Untitled Blueprint")
    description = data.get("description", "")
    domain = data.get("domain", "")
    requests_data = data.get("requests", requests_store)

    # Filter to only include API-like requests
    api_requests = []
    for req in requests_data:
        url = req.get("url", "")
        if not url.startswith("http"):
            continue
        # Mask sensitive data before saving blueprint
        masked = mask_request(req)
        api_requests.append({
            "url": masked.get("url"),
            "method": masked.get("method"),
            "headers": masked.get("headers"),
            "postData": masked.get("postData"),
            "status": masked.get("status"),
            "responseHeaders": masked.get("responseHeaders"),
        })

    blueprint = {
        "id": f"bp_{int(time.time())}",
        "name": name,
        "description": description,
        "domain": domain,
        "version": "1.0",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endpoints": api_requests,
        "endpoint_count": len(api_requests),
    }

    blueprints_store.append(blueprint)

    return {"status": "ok", "blueprint": blueprint}


@app.get("/blueprints")
async def list_blueprints():
    """List all saved blueprints"""
    return {
        "blueprints": [
            {"id": bp["id"], "name": bp["name"], "domain": bp["domain"],
             "endpoint_count": bp["endpoint_count"], "created_at": bp["created_at"]}
            for bp in blueprints_store
        ],
        "total": len(blueprints_store),
    }


@app.get("/blueprints/{blueprint_id}")
async def get_blueprint(blueprint_id: str):
    """Get a specific blueprint by ID"""
    bp = next((b for b in blueprints_store if b["id"] == blueprint_id), None)
    if not bp:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    return bp


@app.post("/blueprints/{blueprint_id}/load")
async def load_blueprint(blueprint_id: str):
    """Load a blueprint's requests into the active store"""
    bp = next((b for b in blueprints_store if b["id"] == blueprint_id), None)
    if not bp:
        raise HTTPException(status_code=404, detail="Blueprint not found")

    global requests_store
    requests_store = list(bp["endpoints"])
    return {"status": "ok", "loaded": len(requests_store), "blueprint": bp["name"]}


@app.post("/blueprints/export")
async def export_blueprint(data: dict[str, Any]):
    """Export a blueprint as downloadable JSON"""
    blueprint_id = data.get("id")
    bp = next((b for b in blueprints_store if b["id"] == blueprint_id), None)
    if not bp:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    return bp


# ─── Background Scheduling Endpoints ───
@app.post("/schedule")
async def create_schedule(data: dict[str, Any]):
    """Create a background watch/schedule task"""
    import time

    task = {
        "id": f"watch_{int(time.time())}",
        "name": data.get("name", "Untitled Watch"),
        "url": data.get("url"),
        "method": data.get("method", "GET"),
        "headers": data.get("headers", {}),
        "body": data.get("body"),
        "condition": data.get("condition", {}),  # e.g. {"status": 200, "body_contains": "available"}
        "interval_seconds": data.get("interval_seconds", 30),
        "action": data.get("action", {}),  # e.g. {"method": "POST", "url": "...", "body": "..."}
        "status": "active",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_check": None,
        "check_count": 0,
        "triggered": False,
    }

    scheduled_watches.append(task)
    return {"status": "ok", "task": task}


@app.get("/schedule")
async def list_schedules():
    """List all scheduled watches"""
    return {"watches": scheduled_watches, "total": len(scheduled_watches)}


@app.post("/schedule/{task_id}/check")
async def check_schedule(task_id: str):
    """Manually check a scheduled task (poll the endpoint)"""
    import httpx
    import time

    task = next((t for t in scheduled_watches if t["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.request(
                method=task["method"],
                url=task["url"],
                headers=task.get("headers", {}),
                content=task.get("body"),
            )

            task["last_check"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")
            task["check_count"] += 1

            # Check condition
            condition = task.get("condition", {})
            condition_met = True

            if condition.get("status") and response.status_code != condition["status"]:
                condition_met = False
            if condition.get("body_contains") and condition["body_contains"] not in response.text:
                condition_met = False
            if condition.get("body_not_contains") and condition["body_not_contains"] in response.text:
                condition_met = False

            result = {
                "status_code": response.status_code,
                "condition_met": condition_met,
                "body_preview": response.text[:500],
                "check_count": task["check_count"],
            }

            if condition_met and not task["triggered"]:
                task["triggered"] = True
                task["status"] = "triggered"
                result["message"] = "⚡ Condition met! Task triggered!"

                # Execute action if defined
                action = task.get("action", {})
                if action.get("url"):
                    action_resp = await client.request(
                        method=action.get("method", "POST"),
                        url=action["url"],
                        headers=action.get("headers", {}),
                        content=action.get("body"),
                    )
                    result["action_result"] = {
                        "status": action_resp.status_code,
                        "body": action_resp.text[:500],
                    }

            return result

    except Exception as e:
        return {"error": str(e), "check_count": task["check_count"]}


@app.delete("/schedule/{task_id}")
async def delete_schedule(task_id: str):
    """Delete a scheduled task"""
    global scheduled_watches
    scheduled_watches = [t for t in scheduled_watches if t["id"] != task_id]
    return {"status": "ok"}


# MCP Protocol endpoints (for Claude Code integration)
@app.post("/mcp")
async def mcp_endpoint(data: MCPRequest):
    """MCP protocol endpoint"""
    method = data.method
    params = data.params or {}

    if method == "tools/list":
        return {
            "tools": [
                {
                    "name": "get_requests",
                    "description": "Get captured network requests",
                    "inputSchema": {"type": "object", "properties": {"limit": {"type": "number"}}}
                },
                {
                    "name": "analyze_requests",
                    "description": "Analyze requests with AI",
                    "inputSchema": {"type": "object", "properties": {"prompt": {"type": "string"}}}
                },
                {
                    "name": "generate_code",
                    "description": "Generate code from requests",
                    "inputSchema": {"type": "object", "properties": {"language": {"type": "string"}}}
                },
                {
                    "name": "explain_request",
                    "description": "Explain a specific request in detail",
                    "inputSchema": {"type": "object", "properties": {"request": {"type": "object"}}}
                },
                {
                    "name": "clear_requests",
                    "description": "Clear captured requests",
                    "inputSchema": {"type": "object", "properties": {}}
                },
                {
                    "name": "get_config",
                    "description": "Get LLM configuration",
                    "inputSchema": {"type": "object", "properties": {}}
                }
            ]
        }

    elif method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})

        if tool_name == "get_requests":
            return await get_requests(tool_args.get("limit", 100))
        elif tool_name == "analyze_requests":
            return await analyze_requests(AnalyzeRequest(requests=requests_store, prompt=tool_args.get("prompt")))
        elif tool_name == "generate_code":
            return await generate_code({"language": tool_args.get("language", "python")})
        elif tool_name == "explain_request":
            return await explain_request({"request": tool_args.get("request", {})})
        elif tool_name == "clear_requests":
            return await clear_requests()
        elif tool_name == "get_config":
            return await get_config()
        else:
            raise HTTPException(status_code=404, detail=f"Unknown tool: {tool_name}")

    raise HTTPException(status_code=400, detail=f"Unknown method: {method}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
