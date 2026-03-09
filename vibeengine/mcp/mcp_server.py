"""
VibeLens MCP Server (stdio) - Chuẩn Model Context Protocol
Cho phép Claude Code, Antigravity, Cursor kết nối trực tiếp.

Chạy: python -m vibeengine.mcp.mcp_server
Hoặc: uv run mcp run vibeengine/mcp/mcp_server.py
"""

import os
import json
import logging
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load .env
_env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(_env_path)

logger = logging.getLogger("vibelens-mcp")

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────
FASTAPI_URL = os.getenv("VIBELENS_API_URL", "http://localhost:8000")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "dashscope")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen3.5-plus")
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")

# ──────────────────────────────────────────────
# Singleton HTTP Client (Connection Pooling)
# Reuse connections for better performance
# ──────────────────────────────────────────────
_http_client: httpx.AsyncClient | None = None


async def get_http_client() -> httpx.AsyncClient:
    """Get or create singleton HTTP client with connection pooling."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=30.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            follow_redirects=True,
        )
    return _http_client


# ──────────────────────────────────────────────
# LLM Helper - Unified interface using litellm
# Supports 100+ providers: OpenAI, Anthropic, DashScope, Ollama, etc.
# ──────────────────────────────────────────────
def _get_litellm_model() -> str:
    """Convert provider/model to litellm format."""
    provider = LLM_PROVIDER.lower()
    if provider == "dashscope":
        return f"openai/{LLM_MODEL}"  # DashScope uses OpenAI-compatible API
    elif provider == "anthropic":
        return f"anthropic/{LLM_MODEL}"
    elif provider == "ollama":
        return f"ollama/{LLM_MODEL}"
    return LLM_MODEL


def _setup_litellm_env() -> None:
    """Setup environment variables for litellm."""
    if LLM_PROVIDER == "dashscope" and DASHSCOPE_API_KEY:
        os.environ["OPENAI_API_KEY"] = DASHSCOPE_API_KEY
        os.environ["OPENAI_API_BASE"] = "https://coding-intl.dashscope.aliyuncs.com/v1"
    elif LLM_PROVIDER == "openai":
        # OPENAI_API_KEY should already be set
        pass


async def _call_llm(messages: list[dict[str, str]], max_tokens: int = 4000) -> str:
    """
    Call LLM using litellm - unified API for 100+ providers.

    Benefits over raw HTTP:
    - One API for all providers
    - Automatic retry with exponential backoff
    - Built-in cost tracking
    - Fallback support
    """
    try:
        from litellm import acompletion

        _setup_litellm_env()
        model = _get_litellm_model()

        response = await acompletion(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.7,
        )
        return response.choices[0].message.content or ""

    except ImportError:
        logger.warning("litellm not installed, falling back to raw HTTP")
        return await _call_llm_fallback(messages)
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        raise


async def _call_llm_fallback(messages: list[dict[str, str]]) -> str:
    """Fallback LLM call using raw HTTP when litellm is not available."""
    client = await get_http_client()

    base_url = "https://coding-intl.dashscope.aliyuncs.com/v1"
    api_key = DASHSCOPE_API_KEY

    if LLM_PROVIDER == "openai":
        base_url = "https://api.openai.com/v1"
        api_key = os.getenv("OPENAI_API_KEY", "")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    resp = await client.post(
        f"{base_url}/chat/completions",
        headers=headers,
        json={"model": LLM_MODEL, "messages": messages},
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


# ──────────────────────────────────────────────
# MCP Server Instance
# ──────────────────────────────────────────────
mcp = FastMCP(
    "VibeLens",
    instructions=(
        "VibeLens là công cụ theo dõi và phân tích network requests. "
        "Dùng các tools để xem requests đã capture từ Chrome Extension, "
        "phân tích API patterns bằng AI, generate code, và thực thi HTTP requests."
    ),
)


# ──────────────────────────────────────────────
# Helper: Gọi FastAPI bridge (with connection pooling)
# ──────────────────────────────────────────────
async def _call_bridge(method: str, endpoint: str, data: dict | None = None) -> dict:
    """Gọi FastAPI bridge server để lấy data từ Chrome Extension."""
    client = await get_http_client()
    url = f"{FASTAPI_URL}{endpoint}"
    try:
        if method == "GET":
            resp = await client.get(url)
        else:
            resp = await client.post(url, json=data or {})
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        return {"error": f"Không kết nối được tới bridge server tại {FASTAPI_URL}. Hãy chạy: python -m vibeengine.mcp.server"}
    except Exception as e:
        return {"error": str(e)}


# ──────────────────────────────────────────────
# MCP Resources
# ──────────────────────────────────────────────
@mcp.resource("vibelens://config")
def get_config() -> str:
    """Cấu hình hiện tại của VibeLens (AI provider, model, API URL)"""
    return json.dumps({
        "api_url": FASTAPI_URL,
        "llm_provider": LLM_PROVIDER,
        "llm_model": LLM_MODEL,
        "dashscope_configured": bool(DASHSCOPE_API_KEY),
    }, indent=2)


@mcp.resource("vibelens://status")
async def get_status() -> str:
    """Trạng thái hệ thống VibeLens (bridge server, số requests đã capture)"""
    result = await _call_bridge("GET", "/")
    return json.dumps(result, indent=2)


# ──────────────────────────────────────────────
# MCP Tools
# ──────────────────────────────────────────────

@mcp.tool()
async def get_captured_requests(limit: int = 50) -> str:
    """
    Lấy danh sách network requests đã được Chrome Extension bắt (capture).
    Trả về URL, method, status, headers của từng request.

    Args:
        limit: Số lượng requests tối đa cần lấy (mặc định 50)
    """
    result = await _call_bridge("GET", f"/requests?limit={limit}")

    if "error" in result:
        return f"❌ Lỗi: {result['error']}"

    requests = result.get("requests", [])
    total = result.get("total", 0)

    if not requests:
        return "📭 Chưa có requests nào được capture. Hãy mở Chrome Extension và click 'Start Recording'."

    lines = [f"📡 Có {total} requests captured (hiển thị {len(requests)}):"]
    lines.append("")

    for i, req in enumerate(requests):
        status = req.get("status", "?")
        method = req.get("method", "?")
        url = req.get("url", "?")
        lines.append(f"  {i+1}. [{status}] {method} {url}")

        if req.get("headers"):
            # Chỉ hiện headers quan trọng
            important = ["authorization", "content-type", "cookie", "x-csrf-token"]
            for key, val in req["headers"].items():
                if key.lower() in important:
                    lines.append(f"     ├─ {key}: {val[:80]}")

        if req.get("postData"):
            body = req["postData"][:200]
            lines.append(f"     └─ Body: {body}")

    return "\n".join(lines)


@mcp.tool()
async def get_auth_info() -> str:
    """
    Xem thông tin authentication đã capture: cookies, tracked domains, redirect chains, Set-Cookie headers.
    Dùng tool này để hiểu auth flow và replay login.
    """
    result = await _call_bridge("GET", "/requests?limit=500")
    meta = result.get("meta", {})
    requests = result.get("requests", [])

    lines = ["🔐 Auth Info từ VibeLens Capture:"]
    lines.append("")

    # Tracked domains
    domains = meta.get("trackedDomains", [])
    lines.append(f"── TRACKED DOMAINS ({len(domains)}) ──")
    if domains:
        for d in domains:
            lines.append(f"  • {d}")
    else:
        lines.append("  (no multi-domain tracking)")

    # Captured cookies
    cookies = meta.get("capturedCookies", {})
    lines.append(f"")
    lines.append(f"── CAPTURED COOKIES ──")
    if cookies:
        for domain, cookie_list in cookies.items():
            lines.append(f"  [{domain}] — {len(cookie_list)} cookies:")
            for c in cookie_list[:10]:
                lines.append(f"    • {c.get('name', '?')} = {str(c.get('value', ''))[:50]}...")
            if len(cookie_list) > 10:
                lines.append(f"    ... và {len(cookie_list) - 10} cookies khác")
    else:
        lines.append("  (no cookies captured)")

    # Requests with Set-Cookie
    set_cookie_reqs = [r for r in requests if r.get("setCookies")]
    lines.append(f"")
    lines.append(f"── SET-COOKIE RESPONSES ({len(set_cookie_reqs)}) ──")
    for req in set_cookie_reqs[:10]:
        lines.append(f"  [{req.get('status')}] {req.get('method')} {req.get('url', '')[:80]}")
        for sc in req.get("setCookies", []):
            lines.append(f"    Set-Cookie: {sc[:100]}...")

    # Requests with cookies sent
    cookie_reqs = [r for r in requests if r.get("cookies")]
    lines.append(f"")
    lines.append(f"── REQUESTS WITH COOKIES ({len(cookie_reqs)}) ──")
    for req in cookie_reqs[:10]:
        cookie_str = req.get("cookies", "")
        lines.append(f"  [{req.get('status')}] {req.get('method')} {req.get('url', '')[:60]}")
        lines.append(f"    Cookie: {cookie_str[:150]}...")

    # Redirect chains
    redirect_reqs = [r for r in requests if r.get("redirectChain")]
    lines.append(f"")
    lines.append(f"── REDIRECT CHAINS ({len(redirect_reqs)}) ──")
    for req in redirect_reqs:
        lines.append(f"  🔗 {req.get('method')} {req.get('url', '')[:80]}")
        for step in req.get("redirectChain", []):
            lines.append(f"    → [{step.get('status')}] {step.get('url', '')[:80]}")

    return "\n".join(lines)


@mcp.tool()
async def get_request_detail(index: int) -> str:
    """
    Xem chi tiết đầy đủ của một request cụ thể (headers, payload, response body, timing).
    Giống như click vào request trong Chrome DevTools Network tab.

    Args:
        index: Số thứ tự của request (bắt đầu từ 1, lấy từ danh sách get_captured_requests)
    """
    result = await _call_bridge("GET", "/requests?limit=500")
    requests = result.get("requests", [])

    if not requests:
        return "📭 Chưa có requests nào."

    idx = index - 1
    if idx < 0 or idx >= len(requests):
        return f"❌ Index {index} không hợp lệ. Có {len(requests)} requests (1-{len(requests)})."

    req = requests[idx]

    lines = [f"🔍 Chi tiết Request #{index}:"]
    lines.append(f"")
    lines.append(f"── GENERAL ──")
    lines.append(f"  URL: {req.get('url', 'N/A')}")
    lines.append(f"  Method: {req.get('method', 'N/A')}")
    lines.append(f"  Status: {req.get('status', 'N/A')} {req.get('statusText', '')}")
    lines.append(f"  MIME: {req.get('mimeType', 'N/A')}")
    lines.append(f"  Size: {req.get('responseBodySize', req.get('encodedDataLength', 'N/A'))} bytes")
    lines.append(f"  Completed: {req.get('completed', 'N/A')}")

    # Timing
    timing = req.get("timing")
    if timing:
        lines.append(f"")
        lines.append(f"── TIMING ──")
        lines.append(f"  DNS: {timing.get('dnsEnd', 0) - timing.get('dnsStart', 0):.0f}ms")
        lines.append(f"  Connect: {timing.get('connectEnd', 0) - timing.get('connectStart', 0):.0f}ms")
        lines.append(f"  TTFB: {timing.get('receiveHeadersEnd', 0):.0f}ms")

    # Request Headers
    headers = req.get("headers", {})
    lines.append(f"")
    lines.append(f"── REQUEST HEADERS ({len(headers)} items) ──")
    if headers:
        for key, val in headers.items():
            lines.append(f"  {key}: {val}")
    else:
        lines.append("  (none)")

    # Response Headers
    resp_headers = req.get("responseHeaders", {})
    lines.append(f"")
    lines.append(f"── RESPONSE HEADERS ({len(resp_headers)} items) ──")
    if resp_headers:
        for key, val in resp_headers.items():
            lines.append(f"  {key}: {val}")
    else:
        lines.append("  (none)")

    # Request Body (Payload)
    post_data = req.get("postData")
    lines.append(f"")
    lines.append(f"── REQUEST BODY ──")
    if post_data:
        lines.append(f"  {post_data}")
    else:
        lines.append("  (no payload)")

    # Response Body — smart trimmed based on content type
    resp_body = req.get("responseBody")
    lines.append(f"")
    lines.append(f"── RESPONSE BODY ──")
    if resp_body:
        from vibeengine.mcp.server import smart_trim_body
        trimmed = smart_trim_body(str(resp_body), max_chars=8000, context='detail')
        lines.append(f"  {trimmed}")
    else:
        lines.append("  (no response body captured)")

    return "\n".join(lines)

@mcp.tool()
async def analyze_api_traffic(prompt: str | None = None) -> str:
    """
    Phân tích các API requests đã capture bằng AI.
    AI sẽ tìm ra: endpoints, authentication, patterns, và cách replicate.

    Args:
        prompt: Câu hỏi cụ thể về các requests (tùy chọn).
               Ví dụ: "Tìm endpoint đăng ký môn học" hoặc "Phân tích auth flow"
    """
    # P0: Prefer filtered requests (no noise) over raw requests
    req_result = await _call_bridge("GET", "/requests/filtered?limit=100")
    requests = req_result.get("requests", [])

    # Fallback to unfiltered if filtered returns nothing
    if not requests:
        req_result = await _call_bridge("GET", "/requests?limit=100")
        requests = req_result.get("requests", [])

    if not requests:
        return "📭 Chưa có requests nào. Hãy capture trước rồi phân tích."

    # P0 #1: Build context WITH response body for complete API analysis
    context_lines = []
    for i, req in enumerate(requests[:50]):
        context_lines.append(f"\n--- Request {i+1} ---")
        context_lines.append(f"Method: {req.get('method', 'GET')}")
        context_lines.append(f"URL: {req.get('url', '')}")
        if req.get("headers"):
            context_lines.append(f"Headers: {json.dumps(req['headers'], indent=2)}")
        if req.get("postData"):
            context_lines.append(f"Body: {req['postData']}")
        if req.get("status"):
            context_lines.append(f"Status: {req['status']}")
        # P0 #1: Include response body — smart trimmed by content type
        resp_body = req.get("responseBody") or req.get("response_body")
        if resp_body and not str(resp_body).startswith("[SKIPPED"):
            # Import smart trimmer from server module
            from vibeengine.mcp.server import smart_trim_body
            trimmed = smart_trim_body(str(resp_body), max_chars=3000, context='ai')
            context_lines.append(f"Response: {trimmed}")

    noise_info = ""
    noise_removed = req_result.get("noise_removed", 0)
    if noise_removed > 0:
        noise_info = f"\n(⚡ Smart Filter: {noise_removed} noise requests auto-removed)"

    context = "\n".join(context_lines)

    default_prompt = """Phân tích các API requests sau và cho biết:
1. Các API endpoints và mục đích
2. Phương thức authentication
3. Request/response patterns
4. Code mẫu Python để replicate các calls này
5. Bất kỳ thông tin quan trọng nào khác"""

    messages = [
        {"role": "system", "content": "Bạn là chuyên gia phân tích API. Hãy phân tích các network requests và đưa ra insights chi tiết. Lưu ý: Response body đã được include — hãy dùng nó để hiểu cấu trúc dữ liệu trả về."},
        {"role": "user", "content": f"{prompt or default_prompt}\n\nRequests captured:{noise_info}\n{context}"}
    ]

    try:
        analysis = await _call_llm(messages)
        return f"🤖 AI Analysis ({LLM_MODEL}):{noise_info}\n\n{analysis}"
    except Exception as e:
        return f"❌ Lỗi khi gọi AI: {e}"


@mcp.tool()
async def generate_api_code(language: str = "python") -> str:
    """
    Generate code từ các requests đã capture.
    Tạo code có thể chạy được để replicate các API calls.

    Args:
        language: Ngôn ngữ code (python, javascript, curl). Mặc định: python
    """
    req_result = await _call_bridge("GET", "/requests?limit=100")
    requests = req_result.get("requests", [])

    if not requests:
        return "📭 Chưa có requests nào để generate code."

    # Lọc API requests
    api_requests = [r for r in requests if "/api/" in r.get("url", "")]
    if not api_requests:
        api_requests = requests  # Dùng tất cả nếu không có /api/

    context_lines = []
    for i, req in enumerate(api_requests[:30]):
        context_lines.append(f"\n--- Request {i+1} ---")
        context_lines.append(f"Method: {req.get('method', 'GET')}")
        context_lines.append(f"URL: {req.get('url', '')}")
        if req.get("headers"):
            context_lines.append(f"Headers: {json.dumps(req['headers'], indent=2)}")
        if req.get("postData"):
            context_lines.append(f"Body: {req['postData']}")

    context = "\n".join(context_lines)

    prompts = {
        "python": "Generate executable Python code using 'requests' library to replicate these API calls. Include error handling.",
        "javascript": "Generate executable JavaScript code using 'fetch' or 'axios' to replicate these API calls.",
        "curl": "Convert these API calls to curl commands that can be run directly in terminal.",
    }

    messages = [
        {"role": "system", "content": "You are a code generator. Generate clean, executable code."},
        {"role": "user", "content": f"{prompts.get(language, prompts['python'])}\n\n{context}"}
    ]

    try:
        code = await _call_llm(messages)
        return f"💻 Generated {language} code:\n\n{code}"
    except Exception as e:
        return f"❌ Lỗi: {e}"


@mcp.tool()
async def execute_http_request(
    url: str,
    method: str = "GET",
    headers: str | None = None,
    body: str | None = None,
) -> str:
    """
    Thực thi một HTTP request. Dùng tool này để replicate các API calls đã phân tích.
    ĐÂY LÀ TOOL QUAN TRỌNG — cho phép AI thực sự hành động, không chỉ phân tích.

    Args:
        url: URL đầy đủ (ví dụ: https://api.example.com/endpoint)
        method: HTTP method (GET, POST, PUT, DELETE, PATCH)
        headers: JSON string của headers (ví dụ: '{"Authorization": "Bearer token123"}')
        body: Request body (JSON string hoặc form data)
    """
    parsed_headers = {}
    if headers:
        try:
            parsed_headers = json.loads(headers)
        except json.JSONDecodeError:
            return "❌ Headers phải là JSON hợp lệ"

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        try:
            response = await client.request(
                method=method.upper(),
                url=url,
                headers=parsed_headers,
                content=body,
            )

            # Format response
            lines = [
                f"📨 Response:",
                f"  Status: {response.status_code} {response.reason_phrase}",
                f"  URL: {response.url}",
                f"",
                f"  Response Headers:",
            ]

            for key, val in list(response.headers.items())[:15]:
                lines.append(f"    {key}: {val}")

            lines.append(f"")
            lines.append(f"  Body ({len(response.content)} bytes):")

            # Cố parse JSON
            try:
                body_json = response.json()
                body_str = json.dumps(body_json, indent=2, ensure_ascii=False)
            except Exception:
                body_str = response.text

            # Giới hạn length
            if len(body_str) > 3000:
                body_str = body_str[:3000] + "\n... (truncated)"

            lines.append(body_str)

            return "\n".join(lines)
        except Exception as e:
            return f"❌ Lỗi request: {e}"


@mcp.tool()
async def clear_captured_requests() -> str:
    """Xóa tất cả requests đã capture trong bridge server"""
    result = await _call_bridge("POST", "/clear")
    if "error" in result:
        return f"❌ Lỗi: {result['error']}"
    cleared = result.get("cleared", 0)
    return f"🗑️ Đã xóa {cleared} requests."


@mcp.tool()
async def find_requests_by_pattern(pattern: str) -> str:
    """
    Tìm kiếm requests theo pattern (URL, method, hoặc từ khóa).

    Args:
        pattern: Từ khóa tìm kiếm (ví dụ: "login", "api/register", "POST")
    """
    req_result = await _call_bridge("GET", "/requests?limit=500")
    requests = req_result.get("requests", [])

    if not requests:
        return "📭 Chưa có requests nào."

    pattern_lower = pattern.lower()
    matched = []
    for req in requests:
        url = req.get("url", "").lower()
        method = req.get("method", "").lower()
        post_data = (req.get("postData") or "").lower()

        if pattern_lower in url or pattern_lower in method or pattern_lower in post_data:
            matched.append(req)

    if not matched:
        return f"🔍 Không tìm thấy request nào chứa '{pattern}'."

    lines = [f"🔍 Tìm thấy {len(matched)} requests chứa '{pattern}':"]
    lines.append("")

    for i, req in enumerate(matched[:20]):
        lines.append(f"  {i+1}. [{req.get('status', '?')}] {req.get('method', '?')} {req.get('url', '?')}")
        if req.get("headers"):
            lines.append(f"     Headers: {json.dumps(req['headers'])[:150]}")
        if req.get("postData"):
            lines.append(f"     Body: {req['postData'][:200]}")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# P0 #2: Smart Request Filtering (MCP Tools)
# ──────────────────────────────────────────────
@mcp.tool()
async def smart_filter_requests() -> str:
    """
    Phân loại thông minh requests thành API / Tracking / Static / Preflight.
    Dùng Hybrid 3-Layer Filter:
      Layer 1: Rule-based patterns (27+ patterns, instant)
      Layer 2: Brave adblock engine (EasyList + EasyPrivacy, 83,000+ rules)
      Layer 3: Heuristic fallback
    """
    result = await _call_bridge("POST", "/smart-filter")

    if "error" in result:
        return f"❌ Lỗi: {result['error']}"

    stats = result.get("stats", {})
    total = result.get("total", 0)
    signal_ratio = result.get("signal_ratio", "?")
    noise_removed = result.get("noise_removed", 0)
    engine_loaded = result.get("engine_loaded", False)
    source_breakdown = result.get("source_breakdown", {})

    engine_icon = "🛡️ Brave Engine" if engine_loaded else "⚠️ Rule-only"
    lines = [f"⚡ Hybrid Smart Filter Results ({engine_icon}):"]
    lines.append(f"")
    lines.append(f"  📊 Total requests: {total}")
    lines.append(f"  🎯 Signal ratio: {signal_ratio}")
    lines.append(f"  🗑️ Noise removed: {noise_removed}")
    lines.append(f"")
    lines.append(f"  ── Category Breakdown ──")
    lines.append(f"  🟢 API requests:     {stats.get('api', 0)}")
    lines.append(f"  🟡 Other requests:   {stats.get('other', 0)}")
    lines.append(f"  🔴 Tracking/Ads:     {stats.get('tracking', 0)}")
    lines.append(f"  ⚪ Static assets:    {stats.get('static', 0)}")
    lines.append(f"  ⭕ Preflight (CORS): {stats.get('preflight', 0)}")

    # Detection source breakdown
    if source_breakdown:
        lines.append(f"")
        lines.append(f"  ── Detection Source ──")
        for src, count in source_breakdown.items():
            icon = {"rule": "📏", "adblock": "🛡️", "heuristic": "🔮"}.get(src, "❓")
            lines.append(f"  {icon} {src}: {count} requests")

    # Show classified details
    classifications = result.get("classifications", [])
    if classifications:
        lines.append(f"")
        lines.append(f"  ── Classifications (top 20) ──")
        for i, c in enumerate(classifications[:20]):
            cat_icon = {"api": "🟢", "tracking": "🔴", "static": "⚪", "preflight": "⭕", "other": "🟡"}.get(c["category"], "?")
            conf = f"{c['confidence']:.0%}"
            lines.append(f"  {i+1}. {cat_icon} [{c['method']}] {c['url'][:80]}")
            lines.append(f"      → {c['category']} ({conf}, {c['source']}: {c['reason']})")

    return "\n".join(lines)


@mcp.tool()
async def get_filtered_requests(limit: int = 50) -> str:
    """
    Lấy danh sách requests ĐÃ LỌC (tự động loại bỏ tracking, static, preflight).
    Chỉ trả về API requests và requests quan trọng.
    Dùng tool này thay vì get_captured_requests để có dữ liệu sạch hơn.

    Args:
        limit: Số lượng requests tối đa (mặc định 50)
    """
    result = await _call_bridge("GET", f"/requests/filtered?limit={limit}")

    if "error" in result:
        return f"❌ Lỗi: {result['error']}"

    requests = result.get("requests", [])
    total = result.get("total", 0)
    original = result.get("original_total", 0)
    noise = result.get("noise_removed", 0)

    if not requests:
        return "📭 Không có API requests nào sau khi lọc."

    lines = [f"📡 {total} API requests (đã lọc {noise} noise từ {original} tổng):"]
    lines.append("")

    for i, req in enumerate(requests):
        status = req.get("status", "?")
        method = req.get("method", "?")
        url = req.get("url", "?")
        has_body = '📦' if req.get('responseBody') and not str(req.get('responseBody', '')).startswith('[SKIPPED') else ''
        lines.append(f"  {i+1}. [{status}] {method} {url[:120]} {has_body}")

        if req.get("headers"):
            important = ["authorization", "content-type", "cookie", "x-csrf-token"]
            for key, val in req["headers"].items():
                if key.lower() in important:
                    lines.append(f"     ├─ {key}: {val[:80]}")

        if req.get("postData"):
            body = req["postData"][:200]
            lines.append(f"     └─ Body: {body}")

    lines.append("")
    lines.append("💡 Tip: 📦 = có response body captured. Dùng get_request_detail(index) để xem chi tiết.")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# P0 #3: Cookie Bridge (MCP Tool)
# ──────────────────────────────────────────────
@mcp.tool()
async def export_cookies(domain: str | None = None, format: str = "dict") -> str:
    """
    Export cookies đã capture từ browser thành format sẵn sàng dùng trong script.
    Cookies được trích xuất từ Chrome API + request headers.

    Args:
        domain: Lọc theo domain (ví dụ: "shopee.vn"). Bỏ trống = tất cả domains.
        format: Format xuất ra:
                - "dict": Python dictionary {name: value}
                - "header_string": Cookie header string
                - "httpx": Code Python dùng httpx
                - "requests": Code Python dùng requests library
    """
    params = f"/cookies/export?format={format}"
    if domain:
        params += f"&domain={domain}"

    result = await _call_bridge("GET", params)

    if "error" in result:
        return f"❌ {result['error']}\n💡 {result.get('hint', 'Hãy capture requests trước.')}"

    lines = ["🍪 Cookie Export:"]
    lines.append(f"")
    lines.append(f"  Domains: {', '.join(result.get('domains', []))}")
    lines.append(f"  Total cookies: {result.get('total_cookies', 0)}")

    # Show per-domain breakdown
    by_domain = result.get("cookies_by_domain", {})
    if by_domain:
        lines.append(f"")
        for d, count in by_domain.items():
            lines.append(f"  [{d}] — {count} cookies")

    lines.append(f"")

    if format == "dict":
        cookies = result.get("cookies", {})
        lines.append(f"  ── Python Dict ──")
        lines.append(f"  cookies = {{")
        for name, value in cookies.items():
            truncated = "..." if len(value) > 60 else ""
            lines.append(f'    "{name}": "{value[:60]}{truncated}",')
        lines.append(f"  }}")
    elif format == "header_string":
        lines.append(f"  ── Cookie Header ──")
        lines.append(f"  {result.get('cookie_header', '')}")
    elif format in ("httpx", "requests"):
        lines.append(f"  ── Generated Code ({format}) ──")
        lines.append(result.get("code", "# No code generated"))

    return "\n".join(lines)


# ──────────────────────────────────────────────
# P1 #4: Token Lifetime Detection (MCP Tool)
# ──────────────────────────────────────────────
@mcp.tool()
async def analyze_token_lifetime(domain: str | None = None) -> str:
    """
    Phân tích thời gian sống (TTL) của tất cả tokens/cookies đã capture.
    Phát hiện tokens hết hạn, cảnh báo tokens sắp hết hạn, decode JWT.

    Tính năng:
    - Decode JWT tokens để check claim `exp` (expiration)
    - Parse Set-Cookie Expires/Max-Age attributes
    - Nhận diện tokens ngắn hạn nổi tiếng (TikTok msToken, Shopee af-ac-enc-dat, Cloudflare __cf_bm...)
    - Đánh giá khả năng tái sử dụng từng token

    Args:
        domain: Lọc theo domain (ví dụ: "tiktok.com"). Bỏ trống = tất cả domains.
    """
    params = "/tokens/analyze"
    if domain:
        params += f"?domain={domain}"

    result = await _call_bridge("GET", params)

    if "error" in result:
        return f"❌ {result['error']}\n💡 {result.get('hint', 'Hãy capture requests trước.')}"

    summary = result.get("summary", {})
    warnings = result.get("warnings", [])
    tokens_by_domain = result.get("tokens_by_domain", {})
    recommendation = result.get("recommendation", "")

    lines = ["🔍 Token Lifetime Analysis"]
    lines.append("")
    lines.append(f"── SUMMARY ──")
    lines.append(f"  Total tokens:    {summary.get('total_tokens', 0)}")
    lines.append(f"  ⛔ Expired:      {summary.get('expired', 0)}")
    lines.append(f"  🔴 Short-lived:  {summary.get('short_lived', 0)}")
    lines.append(f"  ♻️ Reusable:     {summary.get('reusable', 0)}")
    lines.append(f"  Domains:         {summary.get('domains_analyzed', 0)}")
    lines.append("")

    # Warnings
    if warnings:
        lines.append(f"── ⚠️ WARNINGS ({len(warnings)}) ──")
        for w in warnings[:15]:
            lines.append(f"  {w}")
        if len(warnings) > 15:
            lines.append(f"  ... và {len(warnings) - 15} cảnh báo khác")
        lines.append("")

    # Per-domain details
    for d, analyses in tokens_by_domain.items():
        lines.append(f"── [{d}] — {len(analyses)} tokens ──")
        for a in analyses:
            status_icon = "🟢"
            if not a.get("reusable"):
                status_icon = "⛔"
            elif a.get("ttl_warning"):
                status_icon = "🟡"

            token_type = a.get("type", "unknown")
            line = f"  {status_icon} {a['name']} ({token_type}, {a['length']}ch)"
            lines.append(line)

            if a.get("ttl_warning"):
                lines.append(f"     ⚠️ {a['ttl_warning']}")

            jwt = a.get("jwt_info")
            if jwt:
                lines.append(f"     JWT: {jwt.get('status', '?')} — expires: {jwt.get('expires_at', '?')}")
                if jwt.get("remaining_seconds") is not None:
                    remaining = jwt["remaining_seconds"]
                    if remaining > 3600:
                        lines.append(f"     Remaining: {remaining//3600}h {(remaining%3600)//60}m")
                    elif remaining > 0:
                        lines.append(f"     Remaining: {remaining//60}m {remaining%60}s")
                    else:
                        lines.append(f"     ⛔ Expired {abs(remaining)}s ago")
        lines.append("")

    # Set-Cookie Expiry info
    set_cookies = result.get("set_cookie_expiry", [])
    if set_cookies:
        lines.append(f"── SET-COOKIE EXPIRY ({len(set_cookies)}) ──")
        for sc in set_cookies[:10]:
            ttl = sc.get("expires_in_seconds")
            if ttl is not None:
                if ttl < 300:
                    icon = "🔴"
                elif ttl < 3600:
                    icon = "🟡"
                else:
                    icon = "🟢"
                lines.append(f"  {icon} {sc['cookie_name']} — TTL: {ttl}s ({ttl//60}min)")
            elif sc.get("is_session_cookie"):
                lines.append(f"  🔵 {sc['cookie_name']} — Session cookie (no explicit expiry)")
        lines.append("")

    lines.append(f"📋 {recommendation}")

    return "\n".join(lines)


@mcp.tool()
async def setup_token_refresh(
    action: str = "status",
    domain: str | None = None,
    interval_seconds: int = 60,
    callback_url: str | None = None,
) -> str:
    """
    Quản lý Auto-Refresh cho tokens/cookies.
    Khi bật, VibeLens sẽ tự động kiểm tra token expiration và cảnh báo khi cần refresh.

    Args:
        action: Hành động — "start" (bật), "stop" (tắt), "status" (xem trạng thái)
        domain: Domain cần monitor (ví dụ: "shopee.vn"). Bỏ trống = tất cả.
        interval_seconds: Khoảng thời gian giữa mỗi lần check (giây, mặc định 60)
        callback_url: URL webhook để nhận thông báo khi tokens hết hạn (tùy chọn)
    """
    data = {
        "action": action,
        "domain": domain or "*",
        "interval_seconds": interval_seconds,
    }
    if callback_url:
        data["callback_url"] = callback_url

    result = await _call_bridge("POST", "/tokens/auto-refresh", data)

    if "error" in result:
        return f"❌ {result['error']}"

    if action == "start":
        return (
            f"✅ Auto-refresh đã bật!\n"
            f"  Domain: {data['domain']}\n"
            f"  Interval: {interval_seconds}s\n"
            f"  Task ID: {result.get('task_id', '?')}\n"
            f"  📡 {result.get('message', '')}"
        )
    elif action == "stop":
        return f"⏹️ {result.get('message', 'Đã dừng auto-refresh')}"
    else:
        # Status
        tasks = result.get("tasks", [])
        lines = [f"🔄 Token Auto-Refresh Status"]
        lines.append(f"  Running: {'✅ Yes' if result.get('running') else '❌ No'}")
        lines.append(f"  Active tasks: {result.get('active_count', 0)}")
        lines.append("")

        if tasks:
            for t in tasks:
                status_icon = "🟢" if t["status"] == "active" else "⏹️"
                lines.append(f"  {status_icon} [{t['id']}]")
                lines.append(f"    Domain: {t.get('domain', '*')}")
                lines.append(f"    Interval: {t.get('interval_seconds')}s")
                lines.append(f"    Checks: {t.get('check_count', 0)}")
                lines.append(f"    Last check: {t.get('last_check', 'never')}")

                expired = t.get("expired_tokens", [])
                if expired:
                    lines.append(f"    ⚠️ Expired tokens: {', '.join(expired)}")

                warnings = t.get("warnings", [])
                if warnings:
                    lines.append(f"    Warnings ({len(warnings)}):")
                    for w in warnings[:5]:
                        lines.append(f"      • {w}")
                lines.append("")
        else:
            lines.append("  No refresh tasks configured.")
            lines.append("  Use action='start' to begin monitoring.")

        return "\n".join(lines)


# ──────────────────────────────────────────────
# Feature: Sensitive Data Masking
# ──────────────────────────────────────────────
@mcp.tool()
async def toggle_masking(enabled: bool = True) -> str:
    """
    Bật/tắt tính năng Sensitive Data Masking.
    Khi bật, dữ liệu nhạy cảm (Authorization, Cookie, Password...) sẽ bị che trước khi gửi cho AI.

    Args:
        enabled: True = bật masking, False = tắt masking
    """
    result = await _call_bridge("POST", "/masking", {"enabled": enabled})
    if "error" in result:
        return f"❌ Lỗi: {result['error']}"
    status = "BẬT 🛡️" if enabled else "TẮT ⚠️"
    return f"🔒 Sensitive Data Masking đã được {status}"


# ──────────────────────────────────────────────
# Feature: Vibe Blueprints
# ──────────────────────────────────────────────
@mcp.tool()
async def create_blueprint(name: str, description: str = "", domain: str = "") -> str:
    """
    Tạo Vibe Blueprint từ các requests đã capture.
    Blueprint là "kịch bản mạng" có thể chia sẻ/tái sử dụng cho cộng đồng.

    Args:
        name: Tên blueprint (ví dụ: "Đăng ký môn học HCMUS")
        description: Mô tả (tùy chọn)
        domain: Domain liên quan (ví dụ: "portal.hcmus.edu.vn")
    """
    result = await _call_bridge("POST", "/blueprints", {
        "name": name,
        "description": description,
        "domain": domain,
    })

    if "error" in result:
        return f"❌ Lỗi: {result['error']}"

    bp = result.get("blueprint", {})
    return (
        f"📋 Blueprint '{bp.get('name')}' đã tạo thành công!\n"
        f"  ID: {bp.get('id')}\n"
        f"  Domain: {bp.get('domain', 'N/A')}\n"
        f"  Endpoints: {bp.get('endpoint_count', 0)}\n"
        f"  Created: {bp.get('created_at')}\n\n"
        f"💡 Chia sẻ ID này cho cộng đồng hoặc dùng tool 'load_blueprint' để nạp lại."
    )


@mcp.tool()
async def list_blueprints() -> str:
    """Xem danh sách các Vibe Blueprints đã tạo."""
    result = await _call_bridge("GET", "/blueprints")

    if "error" in result:
        return f"❌ Lỗi: {result['error']}"

    blueprints = result.get("blueprints", [])
    if not blueprints:
        return "📭 Chưa có blueprint nào. Dùng tool 'create_blueprint' để tạo."

    lines = [f"📋 Có {len(blueprints)} blueprint(s):"]
    for bp in blueprints:
        lines.append(
            f"  • [{bp['id']}] {bp['name']} — {bp['domain']} "
            f"({bp['endpoint_count']} endpoints, {bp['created_at']})"
        )

    return "\n".join(lines)


@mcp.tool()
async def load_blueprint(blueprint_id: str) -> str:
    """
    Nạp một Blueprint vào request store để AI phân tích.

    Args:
        blueprint_id: ID của blueprint (ví dụ: "bp_1709654321")
    """
    result = await _call_bridge("POST", f"/blueprints/{blueprint_id}/load")

    if "error" in result:
        return f"❌ Lỗi: {result['error']}"

    return (
        f"✅ Đã nạp blueprint '{result.get('blueprint')}' — "
        f"{result.get('loaded', 0)} endpoints vào store."
    )


# ──────────────────────────────────────────────
# Feature: Background Scheduling
# ──────────────────────────────────────────────
@mcp.tool()
async def schedule_watch(
    name: str,
    url: str,
    method: str = "GET",
    headers: str | None = None,
    body: str | None = None,
    condition_status: int | None = None,
    condition_body_contains: str | None = None,
    condition_body_not_contains: str | None = None,
    interval_seconds: int = 30,
    action_url: str | None = None,
    action_method: str = "POST",
    action_headers: str | None = None,
    action_body: str | None = None,
) -> str:
    """
    Tạo background watch — theo dõi một endpoint và tự hành động khi điều kiện thỏa mãn.
    Ví dụ: "Canh khi nào còn chỗ trống ở lớp AI thì đăng ký ngay cho tôi."

    Args:
        name: Tên task (ví dụ: "Canh lớp AI còn slot")
        url: URL endpoint cần theo dõi
        method: HTTP method (GET, POST...)
        headers: JSON string của headers (tùy chọn)
        body: Request body (tùy chọn)
        condition_status: Status code kỳ vọng (ví dụ: 200)
        condition_body_contains: Body phải chứa text này (ví dụ: "available")
        condition_body_not_contains: Body KHÔNG được chứa text này (ví dụ: "full")
        interval_seconds: Khoảng thời gian giữa các lần check (giây)
        action_url: URL sẽ gọi khi điều kiện thỏa (ví dụ: endpoint đăng ký)
        action_method: HTTP method cho action
        action_headers: JSON string headers cho action
        action_body: Body cho action request
    """
    parsed_headers = json.loads(headers) if headers else {}
    parsed_action_headers = json.loads(action_headers) if action_headers else {}

    condition = {}
    if condition_status:
        condition["status"] = condition_status
    if condition_body_contains:
        condition["body_contains"] = condition_body_contains
    if condition_body_not_contains:
        condition["body_not_contains"] = condition_body_not_contains

    action = {}
    if action_url:
        action = {
            "url": action_url,
            "method": action_method,
            "headers": parsed_action_headers,
            "body": action_body,
        }

    result = await _call_bridge("POST", "/schedule", {
        "name": name,
        "url": url,
        "method": method,
        "headers": parsed_headers,
        "body": body,
        "condition": condition,
        "interval_seconds": interval_seconds,
        "action": action,
    })

    if "error" in result:
        return f"❌ Lỗi: {result['error']}"

    task = result.get("task", {})
    return (
        f"⏰ Watch '{task.get('name')}' đã tạo thành công!\n"
        f"  ID: {task.get('id')}\n"
        f"  URL: {task.get('url')}\n"
        f"  Interval: mỗi {task.get('interval_seconds')}s\n"
        f"  Condition: {json.dumps(condition)}\n"
        f"  Action: {action_url or 'Chỉ thông báo'}\n\n"
        f"💡 Dùng tool 'check_watch' để kiểm tra thủ công hoặc chạy loop tự động."
    )


@mcp.tool()
async def check_watch(task_id: str) -> str:
    """
    Kiểm tra thủ công một watch task — poll endpoint và xem điều kiện đã thỏa chưa.

    Args:
        task_id: ID của watch task (ví dụ: "watch_1709654321")
    """
    result = await _call_bridge("POST", f"/schedule/{task_id}/check")

    if "error" in result:
        return f"❌ Lỗi: {result['error']}"

    status_code = result.get("status_code", "?")
    condition_met = result.get("condition_met", False)
    check_count = result.get("check_count", 0)
    body_preview = result.get("body_preview", "")[:300]

    status_icon = "✅" if condition_met else "⏳"
    lines = [
        f"{status_icon} Check #{check_count}:",
        f"  Status: {status_code}",
        f"  Condition met: {'YES ⚡' if condition_met else 'NO — tiếp tục chờ...'}",
    ]

    if result.get("message"):
        lines.append(f"  🔔 {result['message']}")

    if result.get("action_result"):
        ar = result["action_result"]
        lines.append(f"  Action executed: {ar.get('status')} — {ar.get('body', '')[:200]}")

    lines.append(f"  Body preview: {body_preview}")

    return "\n".join(lines)


@mcp.tool()
async def list_watches() -> str:
    """Xem danh sách tất cả watch tasks đang hoạt động."""
    result = await _call_bridge("GET", "/schedule")

    if "error" in result:
        return f"❌ Lỗi: {result['error']}"

    watches = result.get("watches", [])
    if not watches:
        return "📭 Chưa có watch nào. Dùng 'schedule_watch' để tạo."

    lines = [f"⏰ Có {len(watches)} watch(es):"]
    for w in watches:
        status_icon = "⚡" if w.get("triggered") else "🔄"
        lines.append(
            f"  {status_icon} [{w['id']}] {w['name']} — {w['status']} "
            f"(checked {w.get('check_count', 0)}x)"
        )

    return "\n".join(lines)


# ──────────────────────────────────────────────
# Sprints 2 & 3: HAR Import & Scrapling
# ──────────────────────────────────────────────

@mcp.tool()
async def import_har(file_path: str) -> str:
    """
    Import HAR file -> Parse -> Lưu thành Session -> Return AI Digest.
    Đây là giải pháp thay thế Export HAR thô.
    
    Args:
        file_path: Đường dẫn tuyệt đối tới file .har
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            har_data = json.load(f)
            
        entries = har_data.get('log', {}).get('entries', [])
        if not entries:
            return "❌ File HAR không có network entries hợp lệ."
            
        requests = []
        domain = "har.import"
        
        for entry in entries:
            req = entry.get('request', {})
            res = entry.get('response', {})
            
            url = req.get('url', '')
            if not url.startswith('http'): continue
            
            headers = {h['name']: h['value'] for h in req.get('headers', [])}
            res_headers = {h['name']: h['value'] for h in res.get('headers', [])}
            
            post_data = req.get('postData', {}).get('text', '')
            res_body = res.get('content', {}).get('text', '')
            
            vibelens_req = {
                "url": url,
                "method": req.get('method', 'GET'),
                "headers": headers,
                "responseHeaders": res_headers,
                "postData": post_data,
                "responseBody": res_body,
                "status": res.get('status', 0),
                "mimeType": res.get('content', {}).get('mimeType', '')
            }
            requests.append(vibelens_req)
            if domain == "har.import":
                from urllib.parse import urlparse
                domain = urlparse(url).netloc
                
        # Create session
        sess_resp = await _call_bridge("POST", "/sessions", {"domain": domain, "name": f"HAR Import ({domain})"})
        session_id = sess_resp.get("session_id")
        
        # Save requests
        await _call_bridge("POST", "/requests", {
            "session_id": session_id,
            "requests": requests
        })
        
        # Ai Digest - Trả về Prompt & Data cho IDE AI tự xử lý (Không cần tốn API Key riêng)
        instruction = f"""✅ Đã import {len(requests)} requests từ HAR thành công! Dữ liệu đã được đưa vào Database.
        
[NHIỆM VỤ CỦA BẠN - AI TRỢ LÝ]:
Dựa vào tập dữ liệu giới hạn dưới đây, hãy tự động phân tích và in ra "VibeLens AI Digest Summary" định dạng Markdown tuyệt đẹp cho người dùng.
Tóm tắt các ý chính:
- 🔐 Auth Flow Summary (Ví dụ: Chuyển hướng SSO, Vị trí Token, Cơ chế Auth)
- 📡 API Endpoints (Gom nhóm nếu có)
- 🍪 Cookies quan trọng (nếu có)
- 📊 Statistics (Tổng view GET/POST)

[DATA - 30 REQUESTS ĐẦU TIÊN]:
{json.dumps(requests[:30], indent=2)}
        """
        
        return instruction
        
    except Exception as e:
        return f"❌ Lỗi khi đọc/parse file HAR: {str(e)}"

@mcp.tool()
async def generate_scrapling_spider(target_name: str = "Crawler") -> str:
    """
    Từ captured data (vừa thao tác xong trên browser bằng VibeLens),
    AI sẽ tự động sinh ra một file mã nguồn Crawler sử dụng library Scrapling (thừa kế cookies, bypass headers).
    Đây là chức năng VibeCrawl!
    
    Args:
        target_name: Tên của class Spider cần gen (VD: HCMUT_LMS)
    """
    result = await _call_bridge("GET", "/requests?limit=100")
    requests = result.get("requests", [])
    
    if not requests:
        return "❌ Bạn chưa có request capture nào. Hãy dùng Chrome Extension để Record thao tác lấy cookie + API trước (VD: Lướt website)."
        
    # Auto-update and read Scrapling Docs (Cách 3)
    import subprocess
    import os
    from pathlib import Path
    
    docs_content = ""
    # Xác định đường dẫn tương đối tới folder Scrapling (ngang hàng với vibelens)
    # __file__ = vibelens/vibeengine/mcp/mcp_server.py
    scrapling_dir = Path(__file__).resolve().parents[3] / "Scrapling"
    
    if scrapling_dir.exists():
        try:
            # Bước 1: Pull code tự động
            # Bỏ tracking lỗi pull nếu offline để server không crash
            subprocess.run(
                ["git", "pull", "origin", "main"], 
                cwd=str(scrapling_dir), 
                capture_output=True, 
                timeout=15
            )
            
            # Bước 2: Đọc file Markdown làm "Sách giáo khoa" cho AI
            spiders_md = scrapling_dir / "docs" / "spiders" / "getting-started.md"
            overview_md = scrapling_dir / "docs" / "overview.md"
            
            docs_parts = []
            if spiders_md.exists():
                # Lấy khoảng 3500 ký tự đầu tiên đủ để học syntax
                docs_parts.append("--- SPIDER QUICKSTART ---\n" + spiders_md.read_text(encoding="utf-8")[:3500])
            if overview_md.exists():
                docs_parts.append("--- OVERVIEW / FETCHING ---\n" + overview_md.read_text(encoding="utf-8")[:2000])
                
            if docs_parts:
                docs_content = "\n\n[TÀI LIỆU SCRAPLING MỚI NHẤT TỪ GITHUB (HÃY TUÂN THỦ NGHIÊM NGẶT)]:\n" + "\n".join(docs_parts)
        except Exception as e:
            logger.error(f"Cannot update/read Scrapling docs: {e}")

    # Lấy các requests chính (REST/JSON hoặc HTML form submission)
    api_requests = [r for r in requests if r.get('method') == 'POST' or ('json' in r.get("mimeType", "").lower())]
    if not api_requests:
        api_requests = requests[:15] # Fallback to first 15 requests
        
    instruction = f"""[NHIỆM VỤ CỦA BẠN - AI TRỢ LÝ]:
Người dùng đang dùng VibeLens để build VibeCrawl (Browser Traffic -> Scrapling Code).
    
Hãy viết 1 file Python Crawler sử dụng framework `Scrapling`.
Tên spider cần tạo: `{target_name}Spider`.

[PHƯƠNG PHÁP]:
1. Phân tích các API và Cookie auth pattern trong data bên dưới (Đây là dữ liệu người dùng đã record từ Browser).
2. Tạo 1 class Scrapling Spider, tự inject Cookies + Headers chuẩn xác vào request để không bị chặn (bypass Cloudflare).
3. Viết vòng lặp theo đúng cú pháp Spider của Scrapling để lấy nội dung theo flow của data.
4. Trả về cho người dùng MÃ NGUỒN PYTHON DỄ ĐỌC VÀ CHUẨN XÁC, kèm theo giải thích ngắn.
{docs_content}

[DATA KHÁCH HÀNG CAPTURE ĐƯỢC]:
{json.dumps(api_requests[:20], indent=2)}
    """
    
    return instruction


# ──────────────────────────────────────────────
# Security Tools (Bug Bounty / Security Research)
# ──────────────────────────────────────────────

@mcp.tool()
async def security_scan(
    tests: str = "all",
    limit: int = 20,
) -> str:
    """
    Quét bảo mật các API endpoints đã capture.
    Tự động test: IDOR, Security Headers, Parameter Fuzzing.

    Args:
        tests: Loại tests (all, idor, headers, fuzz). Mặc định: all
        limit: Số requests tối đa để scan
    """
    from vibeengine.security import SecurityScanner

    result = await _call_bridge("GET", f"/requests/filtered?limit={limit}")
    requests = result.get("requests", [])

    if not requests:
        return "📭 Không có requests để scan. Hãy capture trước."

    test_list = ["idor", "headers", "fuzz"] if tests == "all" else [tests]

    scanner = SecurityScanner()
    try:
        scan_result = await scanner.scan_captured_endpoints(requests, test_list)

        lines = [f"🔒 Security Scan Results:"]
        lines.append(f"")
        lines.append(f"  🎯 Endpoints tested: {scan_result.endpoints_tested}")
        lines.append(f"  ⏱️ Duration: {scan_result.scan_duration:.2f}s")
        lines.append(f"  🚨 Findings: {len(scan_result.findings)}")
        lines.append(f"")

        if scan_result.findings:
            lines.append(f"  ── Vulnerabilities Found ──")

            # Group by severity
            by_severity = {}
            for f in scan_result.findings:
                sev = f.severity.value
                if sev not in by_severity:
                    by_severity[sev] = []
                by_severity[sev].append(f)

            severity_order = ["critical", "high", "medium", "low", "info"]
            for sev in severity_order:
                if sev in by_severity:
                    icons = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢", "info": "ℹ️"}
                    lines.append(f"")
                    lines.append(f"  {icons.get(sev, '?')} {sev.upper()} ({len(by_severity[sev])}):")

                    for finding in by_severity[sev][:5]:
                        lines.append(f"    • {finding.title}")
                        lines.append(f"      {finding.endpoint[:80]}")
                        if finding.evidence:
                            lines.append(f"      Evidence: {finding.evidence[:100]}")
        else:
            lines.append(f"  ✅ No vulnerabilities found!")

        return "\n".join(lines)

    except Exception as e:
        return f"❌ Scan error: {e}"
    finally:
        await scanner.close()


@mcp.tool()
async def test_idor(request_index: int = 1) -> str:
    """
    Test IDOR (Insecure Direct Object Reference) trên một request cụ thể.
    Tự động detect ID parameters và test với các giá trị khác nhau.

    Args:
        request_index: Số thứ tự request (từ 1)
    """
    from vibeengine.security import IDORTester

    result = await _call_bridge("GET", "/requests?limit=500")
    requests = result.get("requests", [])

    idx = request_index - 1
    if idx < 0 or idx >= len(requests):
        return f"❌ Index không hợp lệ. Có {len(requests)} requests."

    req = requests[idx]
    url = req.get("url", "")
    method = req.get("method", "GET")
    headers = req.get("headers", {})
    body = req.get("postData")

    # Extract IDOR parameters
    idor_params = IDORTester.extract_ids_from_url(url)

    if not idor_params:
        return f"ℹ️ Không tìm thấy ID parameters trong request #{request_index}."

    lines = [f"🔓 IDOR Analysis for Request #{request_index}:"]
    lines.append(f"  URL: {url}")
    lines.append(f"  Method: {method}")
    lines.append(f"")
    lines.append(f"  ── Potential IDOR Parameters ──")

    for param_name, value in idor_params:
        lines.append(f"  • {param_name}: {value}")

        variants = IDORTester.generate_idor_variants(value)
        lines.append(f"    Test variants: {variants[:5]}")

    lines.append(f"")
    lines.append(f"💡 Dùng security_scan(tests='idor') để test tự động.")

    return "\n".join(lines)


@mcp.tool()
async def fuzz_parameters(
    request_index: int = 1,
    fuzz_type: str = "all",
) -> str:
    """
    Fuzz parameters trên một request để tìm vulnerabilities.

    Args:
        request_index: Số thứ tự request (từ 1)
        fuzz_type: Loại fuzz (all, sqli, xss, traversal, ssrf)
    """
    from vibeengine.security import ParameterFuzzer

    result = await _call_bridge("GET", "/requests?limit=500")
    requests = result.get("requests", [])

    idx = request_index - 1
    if idx < 0 or idx >= len(requests):
        return f"❌ Index không hợp lệ. Có {len(requests)} requests."

    req = requests[idx]
    url = req.get("url", "")
    method = req.get("method", "GET")
    headers = req.get("headers", {})

    # Extract parameters
    params = ParameterFuzzer.extract_parameters(req)

    if not params:
        return f"ℹ️ Không tìm thấy parameters trong request #{request_index}."

    lines = [f"🎯 Parameter Fuzzing for Request #{request_index}:"]
    lines.append(f"  URL: {url}")
    lines.append(f"  Fuzz type: {fuzz_type}")
    lines.append(f"")
    lines.append(f"  ── Parameters Found ──")

    for param_name, values in params.items():
        lines.append(f"  • {param_name}: {values[0] if values else '(empty)'}")

    payload_counts = {
        "sqli": len(ParameterFuzzer.FUZZ_PAYLOADS["sqli"]),
        "xss": len(ParameterFuzzer.FUZZ_PAYLOADS["xss"]),
        "traversal": len(ParameterFuzzer.FUZZ_PAYLOADS["traversal"]),
        "ssrf": len(ParameterFuzzer.FUZZ_PAYLOADS["ssrf"]),
    }

    lines.append(f"")
    lines.append(f"  ── Payload Counts ──")
    for ptype, count in payload_counts.items():
        lines.append(f"  • {ptype}: {count} payloads")

    lines.append(f"")
    lines.append(f"💡 Dùng security_scan(tests='fuzz') để test tự động.")

    return "\n".join(lines)


@mcp.tool()
async def test_auth_bypass(
    request_index: int = 1,
) -> str:
    """
    Test các kỹ thuật Auth Bypass trên một request.
    Test header manipulation, method override, path tricks.

    Args:
        request_index: Số thứ tự request (từ 1)
    """
    from vibeengine.security import AuthBypassTester

    result = await _call_bridge("GET", "/requests?limit=500")
    requests = result.get("requests", [])

    idx = request_index - 1
    if idx < 0 or idx >= len(requests):
        return f"❌ Index không hợp lệ. Có {len(requests)} requests."

    req = requests[idx]
    url = req.get("url", "")
    headers = req.get("headers", {})

    lines = [f"🔐 Auth Bypass Test for Request #{request_index}:"]
    lines.append(f"  URL: {url}")
    lines.append(f"")
    lines.append(f"  ── Bypass Techniques ──")

    for i, technique in enumerate(AuthBypassTester.BYPASS_TECHNIQUES[:10]):
        lines.append(f"  {i+1}. {list(technique.keys())[0]}: {list(technique.values())[0]}")

    lines.append(f"  ... and {len(AuthBypassTester.BYPASS_TECHNIQUES) - 10} more techniques")
    lines.append(f"")
    lines.append(f"💡 Dùng security_scan() để test tự động tất cả requests.")

    return "\n".join(lines)


@mcp.tool()
async def check_security_headers(url: str = None) -> str:
    """
    Kiểm tra Security Headers của một URL hoặc requests đã capture.

    Args:
        url: URL để check (bỏ trống = dùng requests đã capture)
    """
    from vibeengine.security import SecurityHeaderAnalyzer
    import httpx

    if url:
        # Check single URL
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            try:
                response = await client.get(url)
                headers = dict(response.headers)
                findings = SecurityHeaderAnalyzer.analyze_headers(headers)

                lines = [f"🔒 Security Headers Analysis:"]
                lines.append(f"  URL: {url}")
                lines.append(f"")

                if findings:
                    lines.append(f"  ── Findings ({len(findings)}) ──")
                    for f in findings:
                        sev_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢", "info": "ℹ️"}.get(f.severity.value, "?")
                        lines.append(f"  {sev_icon} {f.title}")
                        lines.append(f"     {f.description}")
                else:
                    lines.append(f"  ✅ All security headers present!")

                return "\n".join(lines)

            except Exception as e:
                return f"❌ Error: {e}"

    else:
        # Check captured requests
        result = await _call_bridge("GET", "/requests/filtered?limit=10")
        requests = result.get("requests", [])

        if not requests:
            return "📭 Không có requests. Hãy capture hoặc cung cấp URL."

        lines = [f"🔒 Security Headers Analysis (from captured requests):"]
        lines.append(f"")

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            for i, req in enumerate(requests[:5]):
                url = req.get("url", "")
                try:
                    response = await client.get(url, headers=req.get("headers", {}))
                    findings = SecurityHeaderAnalyzer.analyze_headers(dict(response.headers))

                    lines.append(f"  ── Request {i+1}: {url[:60]} ──")
                    if findings:
                        for f in findings[:3]:
                            lines.append(f"    • {f.title}")
                    else:
                        lines.append(f"    ✅ All headers present")

                except Exception as e:
                    lines.append(f"  ── Request {i+1}: Error - {str(e)[:50]} ──")

        return "\n".join(lines)


@mcp.tool()
async def hexstrike_status() -> str:
    """
    Kiểm tra kết nối với HexStrike AI server.
    Hiển thị tất cả tools, workflows, và intelligence features có sẵn.
    """
    from vibeengine.security import HexStrikeBridge

    bridge = HexStrikeBridge()
    try:
        available = await bridge.is_available()

        if available:
            tools = bridge.list_tools()
            workflows = bridge.list_workflows()
            intel = bridge.list_intelligence()
            caps = bridge.get_all_capabilities()
            
            lines = [f"✅ HexStrike AI Server: Connected"]
            lines.append(f"  URL: {bridge.server_url}")
            lines.append(f"  Total capabilities: {caps['total_capabilities']}")
            lines.append(f"")
            
            lines.append(f"  ── 🔧 Security Tools ({len(tools)}) ──")
            categories = {
                "🌐 Web Scan": ["nuclei", "gobuster", "dirb", "dirsearch", "nikto", "ffuf", "wfuzz",
                               "wpscan", "sqlmap", "feroxbuster", "katana", "httpx", "zap"],
                "🎯 XSS/Fuzzing": ["dalfox", "xsser", "jaeles", "dotdotpwn", "arjun", "x8", "paramspider"],
                "🔌 API Security": ["api_fuzzer", "api_schema_analyzer", "graphql_scanner", "jwt_analyzer"],
                "🔍 Network": ["nmap", "nmap-advanced", "rustscan", "masscan", "autorecon", "arp-scan", "nbtscan"],
                "🔐 Auth/Exploit": ["metasploit", "msfvenom", "hydra", "john", "hashcat", "netexec", "responder"],
                "🕵️ Recon/OSINT": ["amass", "subfinder", "enum4linux", "enum4linux-ng", "smbmap", "rpcclient",
                                   "dnsenum", "fierce", "waybackurls", "gau", "hakrawler", "wafw00f"],
                "☁️ Cloud/K8s": ["prowler", "trivy", "scout-suite", "cloudmapper", "pacu", "kube-hunter",
                                "kube-bench", "docker-bench-security", "clair", "falco", "checkov", "terrascan"],
                "🏆 Binary/CTF": ["volatility", "volatility3", "binwalk", "ropgadget", "ropper", "checksec",
                                 "xxd", "strings", "objdump", "ghidra", "pwntools", "gdb", "gdb-peda",
                                 "radare2", "angr", "one-gadget", "pwninit", "libc-database"],
                "🔎 Forensics": ["exiftool", "foremost", "steghide"],
                "⚡ Utility": ["anew", "uro", "qsreplace", "hashpump", "browser-agent",
                              "http-framework", "burpsuite-alternative"],
            }
            for cat, cat_tools in categories.items():
                available_tools = [t for t in cat_tools if t in tools]
                if available_tools:
                    lines.append(f"  {cat}: {', '.join(available_tools)}")
            
            lines.append(f"")
            lines.append(f"  ── 🎯 Bug Bounty Workflows ({len(workflows)}) ──")
            for name in workflows:
                lines.append(f"  • {name}")
            
            lines.append(f"")
            lines.append(f"  ── 🧠 Intelligence ({len(intel)}) ──")
            for name in intel:
                lines.append(f"  • {name}")

            lines.append(f"")
            ctf = bridge.list_ctf()
            lines.append(f"  ── 🏴 CTF Suite ({len(ctf)}) ──")
            for name in ctf:
                lines.append(f"  • {name}")

            lines.append(f"")
            vi = bridge.list_vuln_intel()
            lines.append(f"  ── 🛡️ Vuln Intelligence ({len(vi)}) ──")
            for name in vi:
                lines.append(f"  • {name}")

            lines.append(f"")
            lines.append(f"  ── 🤖 AI Payloads (3) ──")
            lines.append(f"  • generate, advanced-generate, test")
            
            lines.append(f"")
            lines.append(f"💡 Cách dùng:")
            lines.append(f"  • hexstrike_execute(command='nmap -sV target.com')")
            lines.append(f"  • hexstrike_tool(tool='nuclei', target='https://target.com')")
            lines.append(f"  • hexstrike_smart_scan(target='https://target.com')")
            lines.append(f"  • hexstrike_workflow(workflow='recon', target='target.com')")

            lines.append(f"")
            lines.append(f"  ── ⚠️ Error Recovery ({len(bridge.ERROR_HANDLING)}) ──")
            for name in bridge.ERROR_HANDLING:
                lines.append(f"  • {name}")

            lines.append(f"")
            lines.append(f"  ── 📊 Process Mgmt ({len(bridge.PROCESS_MGMT)}) ──")
            for name in bridge.PROCESS_MGMT:
                lines.append(f"  • {name}")

            lines.append(f"")
            lines.append(f"  ── 📁 Files ({len(bridge.FILES)}) | 🎨 Visual ({len(bridge.VISUAL)}) | 💾 Cache ({len(bridge.CACHE)}) ──")

            return "\n".join(lines)
        else:
            return f"""❌ HexStrike AI Server: Not available

  URL: {bridge.server_url}

  ── How to Start HexStrike ──
  
  Option 1 (Windows - WSL recommended):
    wsl -d Ubuntu
    cd /mnt/c/.../hexstrike-ai
    pip install -r requirements.txt
    python hexstrike_server.py

  Option 2 (Windows native - limited tools):
    cd hexstrike-ai
    pip install -r requirements.txt
    python hexstrike_server.py
    (Chỉ chạy được nuclei.exe, Python-based tools)

  Option 3 (Docker - best):
    docker run -p 8888:8888 hexstrike-ai

  ⚠️ Nhiều tools (nmap, sqlmap, hydra...) yêu cầu Linux.
  Dùng WSL hoặc Docker để chạy đầy đủ 90+ tools!
"""
    finally:
        await bridge.close()


@mcp.tool()
async def hexstrike_execute(
    command: str,
) -> str:
    """
    Thực thi BẤT KỲ lệnh bảo mật nào qua HexStrike (Terminal Proxy).
    Đây là tool mạnh nhất — AI có thể chạy bất kỳ câu lệnh nào HexStrike hỗ trợ.
    
    Ví dụ:
    - "nmap -sV -p 80,443,8080 target.com"
    - "sqlmap -u 'https://target.com/api?id=1' --batch --dbs"
    - "nuclei -u https://target.com -severity critical,high"
    - "ffuf -u https://target.com/FUZZ -w /usr/share/wordlists/dirb/common.txt"
    - "hydra -l admin -P /usr/share/wordlists/rockyou.txt target.com ssh"
    - "gobuster dir -u https://target.com -w /usr/share/wordlists/dirb/common.txt"

    Args:
        command: Câu lệnh bash đầy đủ để chạy trên HexStrike server
    """
    from vibeengine.security import HexStrikeBridge

    bridge = HexStrikeBridge()
    try:
        available = await bridge.is_available()
        if not available:
            return "❌ HexStrike server không available. Dùng hexstrike_status() để xem hướng dẫn."

        lines = [f"🚀 HexStrike Execute"]
        lines.append(f"  Command: {command}")
        lines.append(f"")

        result = await bridge.run_command(command, use_cache=False)
        
        output = result.get("output", result.get("result", ""))
        error = result.get("error", "")
        
        if error:
            lines.append(f"  ❌ Error: {error}")
        elif output:
            # Truncate very long output
            if len(str(output)) > 3000:
                lines.append(f"  {str(output)[:3000]}")
                lines.append(f"  ... (truncated, {len(str(output))} chars total)")
            else:
                lines.append(f"  {output}")
        else:
            lines.append(f"  {json.dumps(result, indent=2)[:2000]}")

        return "\n".join(lines)

    except Exception as e:
        return f"❌ Execution error: {e}"
    finally:
        await bridge.close()


@mcp.tool()
async def hexstrike_tool(
    tool: str,
    target: str,
    scan_type: str = "",
    ports: str = "",
    additional_args: str = "",
) -> str:
    """
    Gọi trực tiếp một tool cụ thể trên HexStrike qua API chuyên biệt.
    Khác với hexstrike_execute, tool này dùng endpoint /api/tools/<tool>
    có tối ưu tham số và error recovery tự động.

    Available tools (50+):
    - Network: nmap, rustscan, masscan, autorecon, arp-scan
    - Web: nuclei, gobuster, dirb, nikto, ffuf, wpscan, sqlmap, katana, httpx
    - Exploit: metasploit, msfvenom, hydra, john, hashcat, netexec
    - Recon: amass, subfinder, enum4linux, smbmap
    - Cloud: prowler, trivy, checkov, terrascan, kube-hunter
    - CTF: volatility, binwalk, ropgadget, checksec, ghidra, radare2, pwntools

    Args:
        tool: Tên tool (e.g. "nmap", "nuclei", "sqlmap")
        target: URL hoặc IP mục tiêu
        scan_type: Loại scan nếu tool hỗ trợ (e.g. "-sCV" cho nmap)
        ports: Ports cần scan (e.g. "80,443,8080")
        additional_args: Tham số bổ sung
    """
    from vibeengine.security import HexStrikeBridge

    bridge = HexStrikeBridge()
    try:
        available = await bridge.is_available()
        if not available:
            return "❌ HexStrike server không available. Dùng hexstrike_status() để xem hướng dẫn."

        params = {"target": target}
        if scan_type:
            params["scan_type"] = scan_type
        if ports:
            params["ports"] = ports
        if additional_args:
            params["additional_args"] = additional_args

        lines = [f"� HexStrike Tool: {tool}"]
        lines.append(f"  Target: {target}")
        if scan_type:
            lines.append(f"  Scan type: {scan_type}")
        if ports:
            lines.append(f"  Ports: {ports}")
        lines.append(f"")

        result = await bridge.call_tool(tool, params)
        
        output = result.get("output", result.get("result", ""))
        error = result.get("error", "")
        
        if error:
            lines.append(f"  ❌ Error: {error}")
        elif output:
            if len(str(output)) > 3000:
                lines.append(f"  {str(output)[:3000]}")
                lines.append(f"  ... (truncated)")
            else:
                lines.append(f"  {output}")
        else:
            lines.append(f"  {json.dumps(result, indent=2)[:2000]}")

        return "\n".join(lines)

    except Exception as e:
        return f"❌ Tool error: {e}"
    finally:
        await bridge.close()


@mcp.tool()
async def hexstrike_smart_scan(
    target: str,
    objective: str = "comprehensive",
    max_tools: int = 5,
) -> str:
    """
    AI Smart Scan — HexStrike tự động chọn tools tối ưu dựa trên target.
    Phân tích target type, technology stack, rồi chạy song song nhiều tools.
    
    Đây là cách quét thông minh nhất — không cần biết trước nên dùng tool gì!

    Args:
        target: URL hoặc IP mục tiêu
        objective: Mục tiêu scan:
                   "comprehensive" — toàn diện
                   "vuln" — tập trung tìm lỗ hổng
                   "recon" — trinh sát, thu thập thông tin
                   "web" — chuyên quét web app
        max_tools: Số tools tối đa chạy song song (mặc định 5)
    """
    from vibeengine.security import HexStrikeBridge

    bridge = HexStrikeBridge()
    try:
        available = await bridge.is_available()
        if not available:
            return "❌ HexStrike server không available."

        lines = [f"🧠 HexStrike AI Smart Scan"]
        lines.append(f"  Target: {target}")
        lines.append(f"  Objective: {objective}")
        lines.append(f"  Max tools: {max_tools}")
        lines.append(f"  ⏳ Running (AI selecting optimal tools)...")
        lines.append(f"")

        result = await bridge.smart_scan(target, objective, max_tools)
        
        # Parse smart scan results
        profile = result.get("target_profile", {})
        if profile:
            lines.append(f"  ── Target Profile ──")
            lines.append(f"  Type: {profile.get('target_type', '?')}")
            lines.append(f"  Risk: {profile.get('risk_level', '?')}")
            techs = profile.get("technologies", [])
            if techs:
                lines.append(f"  Tech: {', '.join(techs)}")
            lines.append(f"")
        
        tools_executed = result.get("tools_executed", [])
        if tools_executed:
            lines.append(f"  ── Tools Executed ({len(tools_executed)}) ──")
            for t in tools_executed:
                name = t.get("tool", "?")
                status = t.get("status", "?")
                icon = "✅" if status == "success" else "❌"
                lines.append(f"  {icon} {name}: {status}")
            lines.append(f"")
        
        total_vulns = result.get("total_vulnerabilities", 0)
        if total_vulns > 0:
            lines.append(f"  🔴 Total vulnerabilities found: {total_vulns}")
        
        combined = result.get("combined_output", "")
        if combined:
            if len(combined) > 2000:
                lines.append(combined[:2000])
                lines.append(f"  ... (truncated)")
            else:
                lines.append(combined)

        return "\n".join(lines)

    except Exception as e:
        return f"❌ Smart scan error: {e}"
    finally:
        await bridge.close()


@mcp.tool()
async def hexstrike_workflow(
    workflow: str,
    target: str,
) -> str:
    """
    Chạy Bug Bounty Workflow tự động trên HexStrike.
    Mỗi workflow là một chuỗi tools được phối hợp theo phương pháp chuyên nghiệp.

    Args:
        workflow: Loại workflow:
                  "recon" — Reconnaissance (subdomain, port scan, tech detect)
                  "vuln-hunt" — Vulnerability Hunting (nuclei, sqlmap, xss)
                  "business-logic" — Business Logic Testing
                  "osint" — Open Source Intelligence
                  "file-upload" — File Upload Testing
                  "comprehensive" — Full Assessment (tất cả các bước)
        target: URL hoặc IP mục tiêu
    """
    from vibeengine.security import HexStrikeBridge

    bridge = HexStrikeBridge()
    try:
        available = await bridge.is_available()
        if not available:
            return "❌ HexStrike server không available."

        valid_workflows = bridge.list_workflows()
        if workflow not in valid_workflows:
            return f"❌ Unknown workflow: {workflow}\n✅ Available: {', '.join(valid_workflows.keys())}"

        lines = [f"🎯 HexStrike Bug Bounty Workflow: {workflow}"]
        lines.append(f"  Target: {target}")
        lines.append(f"  ⏳ Running workflow...")
        lines.append(f"")

        result = await bridge.run_workflow(workflow, target)
        
        output = result.get("output", result.get("result", ""))
        error = result.get("error", "")
        
        if error:
            lines.append(f"  ❌ Error: {error}")
        elif output:
            if len(str(output)) > 3000:
                lines.append(f"  {str(output)[:3000]}")
                lines.append(f"  ... (truncated)")
            else:
                lines.append(f"  {output}")
        else:
            lines.append(f"  {json.dumps(result, indent=2)[:2000]}")

        return "\n".join(lines)

    except Exception as e:
        return f"❌ Workflow error: {e}"
    finally:
        await bridge.close()


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────
def main():
    """Run VibeLens MCP Server (stdio transport)"""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
