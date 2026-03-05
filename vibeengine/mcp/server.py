"""
VibeLens MCP Server
Provides network requests to AI agents via Model Context Protocol
"""

import os
import asyncio
import json
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from vibeengine.llm import ChatOpenAI, ChatAnthropic

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
        "version": "0.1.0",
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


@app.post("/requests")
async def add_requests(data: dict[str, Any]):
    """Add captured requests to the store (append)"""
    global requests_store

    requests_data = data.get("requests", [])
    if isinstance(requests_data, list):
        requests_store.extend(requests_data)

    return {"status": "ok", "count": len(requests_store)}


@app.put("/requests")
async def sync_requests(data: dict[str, Any]):
    """Replace all captured requests (sync from extension)"""
    global requests_store, capture_meta

    requests_data = data.get("requests", [])
    if isinstance(requests_data, list):
        requests_store = requests_data

    # Save metadata (cookies, tracked domains)
    meta = data.get("meta", {})
    if meta:
        capture_meta = meta

    return {"status": "ok", "count": len(requests_store)}


@app.get("/requests")
async def get_requests(limit: int = 100):
    """Get captured requests with metadata"""
    return {
        "requests": requests_store[-limit:],
        "total": len(requests_store),
        "meta": capture_meta,
    }


@app.post("/clear")
async def clear_requests():
    """Clear all captured requests"""
    global requests_store
    count = len(requests_store)
    requests_store = []
    return {"status": "ok", "cleared": count}


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


def build_request_context(requests: list[dict[str, Any]]) -> str:
    """Build context string from requests (with masking applied)"""
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
