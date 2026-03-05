# VibeLens - AI-Powered Network Tracker

<p align="center">
  <img src="https://img.shields.io/badge/Version-0.1.0-blue" alt="Version">
  <img src="https://img.shields.io/badge/Python-3.11+-green" alt="Python">
  <img src="https://img.shields.io/badge/License-MIT-orange" alt="License">
</p>

> **Vietnamese: Trình theo dõi network và phân tích API bằng AI**

VibeLens là một nền tảng mạnh mẽ giúp bạn:
- 📡 **Capture** tất cả HTTP/HTTPS requests từ browser
- 🤖 **Phân tích** API với AI (GPT-4, Claude)
- 💻 **Generate** code từ captured requests
- 🔌 **Kết nối** với Claude Code qua MCP Server

---

## 🎯 Use Cases

### 1. API Reverse Engineering

Bạn muốn biết một trang web gọi API như thế nào?

```
1. Mở DevTools Panel của VibeLens
2. Click "Start Recording"
3. Truy cập trang web cần phân tích
4. Click "Analyze with AI"
5. AI sẽ cho bạn biết:
   - Các API endpoints
   - Authentication methods
   - Request/Response patterns
   - Code mẫu để replicate
```

### 2. Tạo API Proxy/Client

Bạn cần tạo client code cho một API không có documentation?

```
1. Record các requests từ trang web
2. AI sẽ generate code (Python/JS/curl)
3. Copy và sử dụng!
```

### 3. Debug Network Issues

Gặp lỗi API? Muốn hiểu rõ hơn?

```
1. Record requests khi xảy ra lỗi
2. AI phân tích và đề xuất solutions
```

### 4. Tự động hóa với Claude Code

Sử dụng với Claude Code để tự động hóa:

```
User: "Use VibeLens to analyze the API calls from my last session"
Claude: [Phân tích và đưa ra insights]
```

---

## 🚀 Quick Start

### Mode 1: API Mode (Qua API)

```bash
# Install
pip install -e .

# Run MCP Server
python -m vibeengine.mcp.server

# Load extension
# chrome://extensions/ → Load unpacked → extension/
```

### Mode 2: Claude Code / IDE Integration

Kết nối trực tiếp với Claude Code, Cursor, Antigravity:

```bash
# 1. MCP Server chạy ở background
python -m vibeengine.mcp.server

# 2. Trong Claude Code, chỉ cần nói:
# "Use VibeLens to analyze the API calls from my last session"

# 3. AI sẽ:
# - Đọc captured requests
# - Phân tích payload
# - Tự execute requests qua terminal
```

---

## ⚡ 2 Operating Modes

### Mode 1: API Mode (Qua HTTP API)
- Gửi requests qua HTTP endpoints
- Phù hợp cho external tools, simple integration
- AI providers: OpenAI, Anthropic, DashScope (Alibaba)

### Mode 2: Claude Code Integration (Trực tiếp IDE/CLI)
- Kết nối trực tiếp với Claude Code, Cursor, Antigravity
- AI đọc requests và tự thực hiện
- Không cần qua API trung gian

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    VibeLens Architecture                   │
└─────────────────────────────────────────────────────────────┘

  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
  │  Chrome   │    │   MCP     │    │ Claude    │
  │ Extension │───▶│  Server   │───▶│ Code/IDE  │
  └─────────────┘    └─────────────┘    └─────────────┘
                            │
                            ▼
                     ┌─────────────┐
                     │ AI Provider │
                     │ - OpenAI   │
                     │ - Claude   │
                     │ - DashScope│
                     └─────────────┘
```

---

## 🔧 Configuration

### AI Providers

```bash
# OpenAI
LLM_PROVIDER=openai LLM_MODEL=gpt-4 OPENAI_API_KEY=sk-...

# Anthropic
LLM_PROVIDER=anthropic LLM_MODEL=claude-sonnet-4-20250514 ANTHROPIC_API_KEY=sk-ant-...

# Alibaba DashScope (Vietnamese recommended ⭐)
LLM_PROVIDER=dashscope LLM_MODEL=qwen-plus DASHSCOPE_API_KEY=sk-...
```

### Claude Code Integration

```bash
# Auto-configured when MCP server running
# Just tell Claude: "Use VibeLens to analyze..."
```

---

## 📖 Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                     User Workflow                              │
└─────────────────────────────────────────────────────────────────┘

  ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
  │  Browse  │────▶│  Record  │────▶│ Analyze │────▶│ Generate │
  │   Web   │     │ Requests │     │   AI    │     │  Code    │
  └──────────┘     └──────────┘     └──────────┘     └──────────┘
                       │             │             │
                       ▼             ▼             ▼
                ┌──────────────────────────────────────┐
                │         MCP Server (localhost:8000)    │
                │  ┌─────────┐  ┌──────────┐       │
                │  │  Store   │  │  GPT-4/  │       │
                │  │ Requests │  │  Claude  │       │
                │  └─────────┘  └──────────┘       │
                └──────────────────────────────────────┘
```

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Server info |
| GET | `/health` | Health check |
| POST | `/requests` | Add requests |
| GET | `/requests` | Get requests |
| POST | `/analyze` | Analyze with AI |
| POST | `/generate` | Generate code |
| POST | `/clear` | Clear requests |

### Examples

```bash
# Analyze requests
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"requests": [{"url": "/api/users", "method": "GET"}]}'

# Generate Python code
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"language": "python"}'

# Get all requests
curl http://localhost:8000/requests
```

---

## 🔧 Configuration

### Environment Variables

```bash
# AI Providers
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# MCP Server
MCP_PORT=8000
```

### Claude Code Integration

```bash
# Cài đặt skill
mkdir -p ~/.claude/skills/vibelens
curl -o ~/.claude/skills/vibelens/SKILL.md \
  https://raw.githubusercontent.com/vibelens/vibelens/main/skills/vibelens/SKILL.md
```

---

## 📁 Project Structure

```
vibelens/
├── vibeengine/           # Main package
│   ├── browser/         # Browser automation
│   ├── agent/          # LLM-driven agent
│   ├── llm/            # AI providers
│   ├── network/         # Network capture
│   ├── fetchers/        # HTTP fetchers
│   ├── proxy/           # Proxy rotation
│   ├── parser/          # HTML parser
│   └── mcp/            # MCP Server ⭐
├── extension/           # Chrome Extension ⭐
├── examples/            # Example scripts
├── SPEC.md              # Detailed specification
└── README.md            # This file
```

---

## 🛠️ Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check .
ruff format .

# Build extension
# (Load extension/ folder in Chrome)
```

---

## 📝 License

MIT License - xem file LICENSE để biết thêm chi tiết.

---

## 🤝 Contributing

Contributions are welcome! Vui lòng đọc CONTRIBUTING.md trước khi submit PR.

---

## ⚠️ Disclaimer

Tool này chỉ dùng cho mục đích học tập và nghiên cứu. Vui lòng tuân thủ Terms of Service của các website khi sử dụng.
