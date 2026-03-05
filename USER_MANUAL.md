# 🔍 Hướng Dẫn Sử Dụng VibeLens (User Manual v1.0)

Chào mừng bạn đến với **VibeLens** — công cụ biến trình duyệt của bạn thành một cỗ máy phân tích mạng (Network Analyzer) kết nối trực tiếp với AI thông qua **Model Context Protocol (MCP)**. 

Thay vì phải mò mẫm F12 Network tab, copy từng cURL hay tìm kiếm headers, VibeLens cho phép AI "nhìn thấy" chính xác những gì trình duyệt gửi/nhận (bao gồm SSO Auth flows, cookies, redirect chains, và API payloads) để tự động viết script crawler/automation cho bạn.

---

## 🛠️ 1. Cài Đặt Hệ Thống (Installation)

### 1.1 Yêu cầu hệ thống
- Python 3.10 trở lên.
- Trình duyệt Google Chrome (hoặc Edge/Brave/Chromium).
- Một IDE có hỗ trợ MCP (Cursor, Claude Code, Vibe/Antigravity hoặc dọn sẵn Cline/RooCode).

### 1.2 Cài đặt thư viện
Mở terminal tại thư mục gốc của dự án (`vibelens/`):

```bash
# 1. Tạo môi trường ảo (khuyên dùng)
python -m venv .venv

# Trên Windows
.venv\Scripts\activate
# Trên Mac/Linux
source .venv/bin/activate

# 2. Cài đặt các thư viện cần thiết
pip install -e .
# Hoặc nếu bạn dùng `uv` (nhanh hơn):
uv pip install -e .
```

### 1.3 Cấu hình AI Provider (.env)
Nếu bạn dự định dùng các tính năng phân tích trực tiếp từ Bridge Server (tùy chọn), hãy tạo file `.env` ở thư mục `vibelens/`:
```env
LLM_PROVIDER=dashscope  # Hoặc openai / anthropic
LLM_MODEL=qwen3.5-plus
DASHSCOPE_API_KEY=sk-xxxx...
```

---

## 🧩 2. Cài Đặt Chrome Extension (The Observer)

Extension đóng vai trò là "Đôi Mắt" của hệ thống, giúp bắt các network traffic, đặc biệt là các luồng đăng nhập phức tạp đa tên miền (Multi-domain SSO).

1. Mở Chrome, truy cập địa chỉ: `chrome://extensions/`
2. Bật chế độ **Developer mode** (Chế độ dành cho nhà phát triển) ở góc trên bên phải.
3. Nhấp vào nút **Load unpacked** (Tải tiện ích đã giải nén).
4. Trỏ đường dẫn đến thư mục `vibelens/extension/` bên trong project của bạn.
5. Ghim (Pin) icon VibeLens (hình con mắt) lên thanh công cụ Chrome để tiện sử dụng.

---

## 🚀 3. Khởi Động Bridge Server

Bridge Server là cầu nối (HTTP) giữa Chrome Extension và IDE của bạn. Extension sẽ gửi dữ liệu requests về đây.

Mở terminal, đảm bảo đã activate `.venv`, chạy lệnh sau. **LƯU Ý:** Bạn phải ĐỂ TERMINAL NÀY CHẠY LIÊN TỤC trong suốt quá trình sử dụng.

```bash
python -m vibeengine.mcp.server
```
*(Server sẽ khởi động và lắng nghe tại `http://localhost:8000`)*

---

## 🤖 4. Kết Nối MCP Server Vào IDE 

Để AI trong IDE của bạn (Cursor, Claude Code,...) có thể đọc và phân tích các requests từ Bridge Server, bạn cần cấu hình công cụ MCP.

### 🔌 Dành cho Cursor / Cline / RooCode (VS Code)
1. Mở Settings của IDE, tìm phần **MCP Servers** (hoặc MCP extension settings).
2. Nhấn **+ Add New MCP Server**.
3. Điền các thông tin sau:
   - **Name:** `vibelens`
   - **Type:** `command`
   - **Command / Executable:** (Chỉ định đường dẫn tuyệt đối đến file python.exe trong môi trường ảo của bạn)
     - VD Windows: `C:\path\to\vibelens\.venv\Scripts\python.exe`
     - VD Mac/Linux: `/path/to/vibelens/.venv/bin/python`
   - **Args (Đối số):** `["-m", "vibeengine.mcp.mcp_server"]`

### 🔌 Dành cho Claude Code (CLI)
Gõ lệnh này vào terminal của bạn (nhớ sửa lại đường dẫn tuyệt đối tới `.venv`):
```bash
claude mcp add vibelens -- "C:\path\to\vibelens\.venv\Scripts\python.exe" -m vibeengine.mcp.mcp_server
```

### 🛠️ Các MCP Tools IDE sẽ nhận được:
- `get_captured_requests`: Lấy danh sách tổng quan các requests đã bắt.
- `get_request_detail`: Xem full payload, headers, response body của 1 request.
- `get_auth_info`: Hiển thị flow đăng nhập (Session cookies, SSO redirect chain, Tracker domains).
- `find_requests_by_pattern`: Tìm kiếm requests theo từ khoá (vd: 'login', 'api').
- `execute_http_request`: Cho phép AI tự động thực thi HTTP call để test API.

---

## 🎬 5. Quy Trình Sử Dụng Chuẩn (The Workflow)

Dưới đây là kịch bản hoàn hảo nhất để bạn tận dụng sức mạnh của VibeLens từ A-Z. Hãy gửi luồng này cho bạn bè của bạn!

**Bước 1: Chuẩn bị**
- Mở Terminal chạy **Bridge Server** (`python -m vibeengine.mcp.server`).
- Bật IDE có cấu hình MCP.

**Bước 2: Record (Bắt dữ liệu) bằng Extension**
1. Mở trang web bạn muốn lấy data (VD: Hệ thống LMS của trường, Trang TMĐT,...).
2. Click vào icon VibeLens trên Chrome, nhấn nút **"Start Recording"** (Extension sẽ chuyển sang giao diện Drag & Drop nổi trên màn hình).
3. Thao tác trên web như người dùng bình thường: Điền username/password, click Đăng nhập, cuộn trang lấy danh sách sản phẩm.
4. (VibeLens lúc này tự động bắt trọn bộ Cookie SSO, Session Ticket, và JSON Response).

**Bước 3: Yêu cầu AI ở IDE làm việc**
Mở chat AI trong IDE của bạn (hoặc Agent) và gõ Prompt:

> *"Tôi vừa record quá trình đăng nhập và xem danh sách môn học qua VibeLens. Hãy dùng các MCP tools hiện có để đọc Auth Info, tìm ra API Endpoint và Session Cookie. Sau đó viết cho tôi một file script Python dùng thư viện `httpx` để tự động login và in ra danh sách môn học."*

**Lúc này AI sẽ:**
1. Tự gọi `get_auth_info()` để thấy Session Cookie & Redirect Chains.
2. Tự gọi `find_requests_by_pattern()` tìm các JSON APIs.
3. Tự gọi `get_request_detail()` chắt lọc cấu trúc request JSON gửi đi.
4. Viết ra file code hoàn chỉnh! Bạn chỉ việc chạy file `python run.py` là xong! 🔥

---

## ❓ FAQ (Câu Hỏi Thường Gặp)

**Q: Extension không bắt được request nào cả (hiện 0 0 0)?**
A: Chắc chắn rằng tab web bạn đang thao tác là tab "Active" (Tab đang mở hiển thị). Ngoài ra, hãy kiểm tra đảm bảo **Bridge Server (`python -m vibeengine.mcp.server`)** đã được bật và đang chạy. Phải tắt Recording và bật lại sau khi Reload trang.

**Q: Tại sao Response Body lại bị cắt (Truncated)?**
A: Để tránh tràn RAM và giúp AI đọc nhanh hơn, VibeLens có cơ chế **Smart Storage**: Chỉ giữ full văn bản JSON (<100KB), cắt các file HTML dài chỉ giữ meta data/forms, và bỏ qua hoàn toàn ảnh, css, js.

**Q: Làm sao để bắt được luồng đăng nhập nhảy qua tên miền khác (ví dụ từ LMS sang web SSO của Microsoft / Trường học)?**
A: Tính năng **Multi-Domain Tracking** đã được kích hoạt mặc định ở v1.0. Khi trình duyệt bị Redirect, VibeLens sẽ tự động bắt luôn cả Cookie của trang SSO đích và gộp chung chuỗi đăng nhập vào cho bạn. AI chỉ việc gọi `get_auth_info()` là hiểu toàn bộ chuỗi này.

---
VibeLens - Make API Reverse Engineering Great Again! 🕵️‍♂️🔥
