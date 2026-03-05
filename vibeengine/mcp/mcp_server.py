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
DASHSCOPE_OPENAI_URL = "https://coding-intl.dashscope.aliyuncs.com/v1"

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
# Helper: Gọi FastAPI bridge
# ──────────────────────────────────────────────
async def _call_bridge(method: str, endpoint: str, data: dict | None = None) -> dict:
    """Gọi FastAPI bridge server để lấy data từ Chrome Extension"""
    async with httpx.AsyncClient(timeout=30.0) as client:
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


async def _call_llm(messages: list[dict[str, str]]) -> str:
    """Gọi LLM (DashScope/OpenAI compatible) trực tiếp"""
    async with httpx.AsyncClient(timeout=60.0) as client:
        headers = {
            "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": LLM_MODEL,
            "messages": messages,
        }

        base_url = DASHSCOPE_OPENAI_URL
        if LLM_PROVIDER == "openai":
            base_url = "https://api.openai.com/v1"
            headers["Authorization"] = f"Bearer {os.getenv('OPENAI_API_KEY', '')}"

        resp = await client.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


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

    # Response Body
    resp_body = req.get("responseBody")
    lines.append(f"")
    lines.append(f"── RESPONSE BODY ──")
    if resp_body:
        lines.append(f"  {resp_body[:5000]}")
        if len(resp_body) > 5000:
            lines.append(f"  ... [showing 5000/{len(resp_body)} chars — use larger limit if needed]")
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
    # Lấy requests từ bridge
    req_result = await _call_bridge("GET", "/requests?limit=100")
    requests = req_result.get("requests", [])

    if not requests:
        return "📭 Chưa có requests nào. Hãy capture trước rồi phân tích."

    # Build context
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

    context = "\n".join(context_lines)

    default_prompt = """Phân tích các API requests sau và cho biết:
1. Các API endpoints và mục đích
2. Phương thức authentication
3. Request/response patterns
4. Code mẫu Python để replicate các calls này
5. Bất kỳ thông tin quan trọng nào khác"""

    messages = [
        {"role": "system", "content": "Bạn là chuyên gia phân tích API. Hãy phân tích các network requests và đưa ra insights chi tiết."},
        {"role": "user", "content": f"{prompt or default_prompt}\n\nRequests captured:\n{context}"}
    ]

    try:
        analysis = await _call_llm(messages)
        return f"🤖 AI Analysis ({LLM_MODEL}):\n\n{analysis}"
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
# Entry point
# ──────────────────────────────────────────────
def main():
    """Run VibeLens MCP Server (stdio transport)"""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
