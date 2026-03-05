# VibeLens - Network Tracker Extension

Chrome extension để capture network requests và gửi cho AI phân tích.

## Installation

1. Mở Chrome và vào `chrome://extensions/`
2. Bật "Developer mode"
3. Click "Load unpacked"
4. Chọn folder `extension/`

## Cách sử dụng

### 1. Start Recording
- Click vào extension icon hoặc mở DevTools Panel (F12)
- Click "Start Recording"
- Browse web bình thường

### 2. Analyze with AI
- Click "Analyze with AI"
- AI sẽ phân tích các requests đã capture
- Hiển thị insights về API endpoints, authentication, patterns

### 3. Generate Code
- Từ analyzed requests, có thể generate code (Python, JavaScript, curl)

## MCP Server

Chạy MCP server để kết nối với AI:

```bash
python -m vibeengine.mcp.server
```

Server chạy tại `http://localhost:8000`

### API Endpoints

- `GET /` - Server info
- `GET /health` - Health check
- `POST /requests` - Add requests
- `GET /requests` - Get requests
- `POST /analyze` - Analyze with AI
- `POST /generate` - Generate code
- `POST /clear` - Clear requests

## Kết nối với Claude Code

Cài đặt skill:

```bash
mkdir -p ~/.claude/skills/vibelens
curl -o ~/.claude/skills/vibe-lens/SKILL.md \
  https://raw.githubusercontent.com/vibelens/vibelens/main/skills/vibe-lens/SKILL.md
```

Sau đó có thể nói với Claude:

```
Use VibeLens to analyze the API calls from my last session
```
