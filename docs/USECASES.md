# VibeLens - Hướng Dẫn Use Cases

> AI-Powered Network Tracker & Browser Automation Platform

---

## Mục Lục

1. [Tổng Quan](#tổng-quan)
2. [Cài Đặt](#cài-đặt)
3. [Use Case 1: API Reverse Engineering](#use-case-1-api-reverse-engineering)
4. [Use Case 2: Phân Tích Auth Flow](#use-case-2-phân-tích-auth-flow)
5. [Use Case 3: Tạo API Client Code](#use-case-3-tạo-api-client-code)
6. [Use Case 4: Background Watch & Automation](#use-case-4-background-watch--automation)
7. [Use Case 5: Tạo Crawler (VibeCrawl)](#use-case-5-tạo-crawler-vibecrawl)
8. [Use Case 6: Import & Phân Tích HAR](#use-case-6-import--phân-tích-har)
9. [Use Case 7: Debug Network Issues](#use-case-7-debug-network-issues)
10. [Use Case 8: Share API Blueprints](#use-case-8-share-api-blueprints)
11. [Tham Khảo Tools](#tham-khảo-tools)

---

## Tổng Quan

VibeLens là công cụ giúp bạn:
- **Capture** tất cả HTTP/HTTPS requests từ browser
- **Phân tích** API bằng AI (GPT-4, Claude, Qwen)
- **Generate** code từ captured requests
- **Tự động hóa** với background tasks

### Kiến Trúc

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Chrome Extension │───▶│  Bridge Server  │───▶│  AI IDE (MCP)   │
│   (Capture)      │    │  (FastAPI)      │    │  (Phân tích)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

---

## Cài Đặt

### 1. Cài Package
```bash
cd vibelens
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -e .
```

### 2. Cài Chrome Extension
1. Mở `chrome://extensions/`
2. Bật **Developer Mode**
3. Click **Load unpacked** → Chọn folder `extension/`

### 3. Chạy Bridge Server
```bash
python -m vibeengine.mcp.server
```

### 4. Kết nối AI IDE

**Claude Code:**
```bash
claude mcp add vibelens -- /path/to/.venv/Scripts/python -m vibeengine.mcp.mcp_server
```

**Cursor / RooCode:**
```json
{
  "mcpServers": {
    "vibelens": {
      "command": "path/to/.venv/Scripts/python.exe",
      "args": ["-m", "vibeengine.mcp.mcp_server"]
    }
  }
}
```

---

## Use Case 1: API Reverse Engineering

### Mục đích
Hiểu cách một website gọi API khi không có documentation.

### Bước 1: Record Traffic
1. Mở website cần phân tích
2. Click VibeLens icon → **Start Recording**
3. Thực hiện các thao tác (login, search, add to cart...)
4. Click **Stop Recording**

### Bước 2: Phân Tích với AI

**Prompt:**
```
Phân tích các API calls từ session vừa record của tôi.
Tìm:
1. Các API endpoints và mục đích
2. Authentication method
3. Request/Response patterns
```

**AI sẽ dùng tools:**
- `get_captured_requests()` - Lấy danh sách requests
- `analyze_api_traffic()` - Phân tích bằng AI
- `get_auth_info()` - Xem auth flow

### Bước 3: Tìm Request Cụ Thể

**Prompt:**
```
Tìm tất cả requests có chứa "login" hoặc "auth"
```

**Tool:** `find_requests_by_pattern("login")`

### Ví Dụ Output
```
📡 Có 47 requests captured:

1. [200] POST https://api.example.com/auth/login
   ├─ content-type: application/json
   └─ Body: {"email": "user@example.com", "password": "***"}

2. [200] GET https://api.example.com/user/profile
   ├─ authorization: Bearer eyJ...
```

---

## Use Case 2: Phân Tích Auth Flow

### Mục đích
Hiểu authentication flow để replicate login.

### Bước 1: Record Login Flow
1. Bật Recording
2. Đăng nhập vào website
3. Dừng Recording

### Bước 2: Xem Auth Info

**Prompt:**
```
Phân tích auth flow từ session vừa record.
Cho tôi biết:
- Website dùng authentication gì?
- Cookies nào quan trọng?
- Cách replicate login bằng code?
```

**Tool:** `get_auth_info()`

### Output Mẫu
```
🔐 Auth Info từ VibeLens Capture:

── TRACKED DOMAINS (3) ──
  • sso.university.edu
  • portal.university.edu
  • api.university.edu

── CAPTURED COOKIES ──
  [portal.university.edu] — 5 cookies:
    • session_id = abc123...
    • csrf_token = xyz789...

── SET-COOKIE RESPONSES (2) ──
  [302] POST https://sso.university.edu/login
    Set-Cookie: JSESSIONID=...

── REDIRECT CHAINS (1) ──
  🔗 POST https://sso.university.edu/login
    → [302] https://portal.university.edu/dashboard
```

### Bước 3: Generate Login Code

**Prompt:**
```
Generate Python code để auto-login với auth flow trên
```

**Tool:** `generate_api_code("python")`

---

## Use Case 3: Tạo API Client Code

### Mục đích
Tạo code để replicate API calls từ browser.

### Bước 1: Record API Calls
Record các thao tác cần replicate.

### Bước 2: Generate Code

**Python:**
```
Generate Python code từ các requests đã capture
```

**JavaScript:**
```
Generate JavaScript/fetch code cho các API calls này
```

**cURL:**
```
Convert các requests thành curl commands
```

### Output Mẫu
```python
import requests

def login(email: str, password: str):
    response = requests.post(
        "https://api.example.com/auth/login",
        headers={"Content-Type": "application/json"},
        json={"email": email, "password": password}
    )
    return response.json()

def get_profile(token: str):
    response = requests.get(
        "https://api.example.com/user/profile",
        headers={"Authorization": f"Bearer {token}"}
    )
    return response.json()
```

---

## Use Case 4: Background Watch & Automation

### Mục đích
Tự động monitor endpoint và trigger action khi điều kiện thỏa.

### Ví Dụ: Canh Slot Học

**Prompt:**
```
Tạo watch task:
- URL: https://university.edu/api/courses/CS101/slots
- Điều kiện: body chứa "available" và KHÔNG chứa "full"
- Action: Gọi POST https://university.edu/api/register với body {"course": "CS101"}
- Interval: mỗi 30 giây
```

**Tool:** `schedule_watch()`

### Bước 1: Tạo Watch Task
```
⏰ Watch 'Course Slot Monitor' đã tạo thành công!
  ID: watch_1709654321
  URL: https://university.edu/api/courses/CS101/slots
  Interval: mỗi 30s
  Condition: {"body_contains": "available", "body_not_contains": "full"}
  Action: POST https://university.edu/api/register
```

### Bước 2: Kiểm Tra

**Manual check:**
```
Kiểm tra watch task xem slot đã available chưa
```

**Tool:** `check_watch("watch_1709654321")`

### Bước 3: Xem Tất Cả Watches
```
Liệt kê tất cả watch tasks đang chạy
```

**Tool:** `list_watches()`

---

## Use Case 5: Tạo Crawler (VibeCrawl)

### Mục đích
Tạo crawler code từ browser session, tự động bypass anti-bot.

### Bước 1: Record Browsing
1. Bật Recording
2. Browse website cần crawl (navigate qua các pages)
3. Đảm bảo đã login nếu cần authenticated pages
4. Dừng Recording

### Bước 2: Generate Spider

**Prompt:**
```
Generate Scrapling spider tên "LMS_Crawler" từ session vừa record
Spider cần:
- Thừa kế cookies từ browser
- Bypass Cloudflare
- Crawl các pages tôi đã duyệt
```

**Tool:** `generate_scrapling_spider("LMSCrawler")`

### Output Mẫu
```python
from scrapling import Fetcher

class LMSCrawler:
    """Auto-generated from VibeLens capture"""

    def __init__(self):
        # Cookies from browser session
        self.cookies = {
            "session_id": "...",
            "csrf_token": "...",
        }
        self.fetcher = Fetcher(impersonate='chrome128')

    def start(self):
        # Step 1: Load main page
        response = self.fetcher.get(
            "https://lms.university.edu/dashboard",
            cookies=self.cookies
        )

        # Step 2: Extract data
        links = response.css('a.course-link::attr(href)')
        for link in links:
            self.crawl_course(link)

    def crawl_course(self, url):
        response = self.fetcher.get(url, cookies=self.cookies)
        # ... extraction logic
```

---

## Use Case 6: Import & Phân Tích HAR

### Mục đích
Phân tích HAR file từ Chrome DevTools với AI digest.

### Bước 1: Export HAR từ Chrome
1. Mở Chrome DevTools (F12)
2. Tab **Network**
3. Click phải → **Save all as HAR with content**

### Bước 2: Import vào VibeLens

**Prompt:**
```
Import HAR file tại C:/Downloads/network.har và phân tích
```

**Tool:** `import_har("C:/Downloads/network.har")`

### Output
```
✅ Đã import 156 requests từ HAR thành công!

[VibeLens AI Digest Summary]

🔐 Auth Flow Summary:
- SSO redirect: sso.example.com → app.example.com
- Token location: Response body (JWT)
- Auth method: Bearer token in Authorization header

📡 API Endpoints (grouped):
- /auth/* - Authentication endpoints
- /api/users/* - User management
- /api/products/* - Product catalog

🍪 Important Cookies:
- session_id (HttpOnly, Secure)
- csrf_token

📊 Statistics:
- Total: 156 requests
- GET: 89 | POST: 42 | PUT: 12 | DELETE: 13
- Domains: 3
```

---

## Use Case 7: Debug Network Issues

### Mục đích
Debug API errors với AI analysis.

### Bước 1: Record Khi Có Lỗi
1. Bật Recording
2. Thực hiện action gây lỗi
3. Dừng Recording

### Bước 2: Tìm Error Requests

**Prompt:**
```
Tìm tất cả requests có status 4xx hoặc 5xx
```

**Tool:** `find_requests_by_pattern("40")` hoặc `find_requests_by_pattern("50")`

### Bước 3: Xem Chi Tiết

**Prompt:**
```
Xem chi tiết request #15 (request bị lỗi)
```

**Tool:** `get_request_detail(15)`

### Bước 4: AI Phân Tích

**Prompt:**
```
Request #15 trả về 401 Unauthorized.
Phân tích xem tại sao và cách fix.
So sánh với request #3 (request thành công).
```

### Output
```
🔍 Phân tích lỗi 401:

Request #15 (Failed):
- URL: /api/user/settings
- Authorization: Bearer expired_token...

Request #3 (Success):
- URL: /api/user/profile
- Authorization: Bearer valid_token...

⚠️ Vấn đề: Token đã hết hạn
💡 Giải pháp: Refresh token hoặc re-login trước khi gọi API
```

---

## Use Case 8: Share API Blueprints

### Mục đích
Lưu và chia sẻ API patterns với cộng đồng.

### Bước 1: Tạo Blueprint

**Prompt:**
```
Tạo blueprint từ session hiện tại:
- Tên: "Đăng ký môn học HCMUS"
- Domain: portal.hcmus.edu.vn
- Mô tả: Flow đăng ký môn học qua API
```

**Tool:** `create_blueprint("HCMUS Course Registration", "...", "portal.hcmus.edu.vn")`

### Output
```
📋 Blueprint 'HCMUS Course Registration' đã tạo thành công!
  ID: bp_1709654321
  Domain: portal.hcmus.edu.vn
  Endpoints: 12
```

### Bước 2: Chia Sẻ
Chia sẻ ID `bp_1709654321` cho cộng đồng.

### Bước 3: Load Blueprint

**Prompt:**
```
Load blueprint bp_1709654321 để phân tích
```

**Tool:** `load_blueprint("bp_1709654321")`

---

## Tham Khảo Tools

### Core Tools

| Tool | Mô tả |
|------|-------|
| `get_captured_requests(limit)` | Lấy danh sách requests |
| `get_request_detail(index)` | Xem chi tiết 1 request |
| `get_auth_info()` | Phân tích authentication |
| `find_requests_by_pattern(pattern)` | Tìm kiếm requests |
| `execute_http_request(...)` | Thực thi HTTP request |

### AI Tools

| Tool | Mô tả |
|------|-------|
| `analyze_api_traffic(prompt)` | Phân tích bằng AI |
| `generate_api_code(language)` | Generate code |

### Advanced

| Tool | Mô tả |
|------|-------|
| `import_har(file_path)` | Import HAR file |
| `generate_scrapling_spider(name)` | Tạo crawler code |
| `toggle_masking(enabled)` | Bật/tắt che dữ liệu nhạy |

### Scheduling

| Tool | Mô tả |
|------|-------|
| `schedule_watch(...)` | Tạo background watch |
| `check_watch(task_id)` | Kiểm tra watch |
| `list_watches()` | Liệt kê watches |

### Blueprints

| Tool | Mô tả |
|------|-------|
| `create_blueprint(...)` | Tạo blueprint |
| `list_blueprints()` | Xem blueprints |
| `load_blueprint(id)` | Load blueprint |

---

## CLI Commands

VibeLens cung cấp CLI để quản lý từ terminal.

### Core Commands

```bash
# Show version
vibelens version

# Check installation
vibelens doctor

# Install Playwright browsers
vibelens install
```

### Server Management

```bash
# Start Bridge Server
vibelens server start --port 8000

# Start MCP Server (for AI IDEs)
vibelens server mcp

# Check server status
vibelens server status
```

### Sessions Management

```bash
# List sessions
vibelens sessions list

# Show session details
vibelens sessions show <session_id>

# Delete session
vibelens sessions delete <session_id>
```

### Requests Management

```bash
# List captured requests
vibelens requests list

# Filter by pattern
vibelens requests list --pattern "api"

# Show request details
vibelens requests show 1

# Clear all requests
vibelens requests clear
```

### HAR Import

```bash
# Import HAR file
vibelens har /path/to/file.har
```

### Blueprints Management

```bash
# List blueprints
vibelens blueprints list

# Create blueprint
vibelens blueprints create --name "My API" --domain "example.com"
```

### Browser Automation

```bash
# Fetch URL with stealth
vibelens fetch https://example.com

# Bypass Cloudflare
vibelens stealth https://protected-site.com --cloudflare

# Interactive browser shell
vibelens shell --url https://example.com

# Extract content
vibelens extract https://example.com output.txt --css ".content"

# Analyze traffic
vibelens analyze https://example.com

# Run AI agent
vibelens run "Find all products on the page"
```

---

## Troubleshooting

### "Bridge server not connected"
```bash
python -m vibeengine.mcp.server
```

### "No requests captured"
- Kiểm tra Chrome Extension đã bật
- Click "Start Recording" trước khi browse

### "AI call failed"
- Kiểm tra `.env` có API keys
- Verify `LLM_PROVIDER` và `LLM_MODEL`

### Requests không đầy đủ
- Tăng `limit` parameter
- Check extension console for errors

---

## Tips & Best Practices

1. **Record riêng từng flow**
   - Login flow → riêng
   - Search flow → riêng
   - Dễ phân tích hơn

2. **Clear trước khi record**
   ```
   Xóa tất cả requests cũ
   ```
   `clear_captured_requests()`

3. **Che dữ liệu nhạy cảm**
   ```
   Bật sensitive data masking
   ```
   `toggle_masking(True)`

4. **Save quan trọng thành Blueprint**
   - Đừng mất session quan trọng
   - Tạo blueprint để backup

---

## License

MIT License - Vui lòng tuân thủ Terms of Service của các website.