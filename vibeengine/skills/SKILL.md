# VibeLens Skill

> AI-Powered Network Tracker & Browser Automation Platform

## Overview

VibeLens captures network traffic from browser, analyzes APIs with AI, and generates executable code. It bridges Chrome Extension ↔ FastAPI Server ↔ AI IDE (via MCP).

## Core Capabilities

### 1. Network Capture & Analysis
- Capture XHR/Fetch requests from any website
- Track multi-domain SSO redirects
- Capture cookies, auth headers, request payloads
- Auto-mask sensitive data (passwords, tokens)

### 2. AI-Powered Analysis
- Understand authentication flows
- Find API patterns
- Generate Python/JS/cURL code
- Debug network issues

### 3. Automation & Scheduling
- Background watch tasks
- Auto-trigger actions when conditions met
- Monitor endpoints continuously

### 4. Crawler Generation
- Auto-generate Scrapling spider code
- Inherit cookies from browser session
- Bypass anti-bot protections

## Tools Reference

### Core Tools

| Tool | Description |
|------|-------------|
| `get_captured_requests(limit)` | Get captured network requests |
| `get_request_detail(index)` | View full request details |
| `get_auth_info()` | Analyze authentication flow |
| `find_requests_by_pattern(pattern)` | Search for specific requests |
| `execute_http_request(url, method, headers, body)` | Execute HTTP request |

### AI Tools

| Tool | Description |
|------|-------------|
| `analyze_api_traffic(prompt)` | AI-powered traffic analysis |
| `generate_api_code(language)` | Generate Python/JS/cURL code |

### Advanced Tools

| Tool | Description |
|------|-------------|
| `import_har(file_path)` | Import HAR file with AI digest |
| `generate_scrapling_spider(name)` | Generate crawler code |
| `toggle_masking(enabled)` | Toggle sensitive data masking |

### Scheduling Tools

| Tool | Description |
|------|-------------|
| `schedule_watch(...)` | Create background watch task |
| `check_watch(task_id)` | Check watch task status |
| `list_watches()` | List all active watches |

### Blueprint Tools

| Tool | Description |
|------|-------------|
| `create_blueprint(name, desc, domain)` | Save requests as blueprint |
| `list_blueprints()` | View saved blueprints |
| `load_blueprint(id)` | Load blueprint into store |

## Usage Patterns

### Pattern 1: API Reverse Engineering

```
User records browser session → AI analyzes → Generate code

Steps:
1. User browses target website with VibeLens recording
2. Ask: "Analyze the API calls from my session"
3. Use: get_captured_requests() → analyze_api_traffic()
4. Ask: "Generate Python code to replicate login"
5. Use: generate_api_code("python")
```

### Pattern 2: Authentication Flow Analysis

```
User logs into website → AI finds auth pattern → Provide login script

Steps:
1. User records login flow
2. Ask: "What authentication does this site use?"
3. Use: get_auth_info() → analyze_api_traffic("find auth flow")
4. AI identifies: cookies, tokens, redirect chains
5. Generate code with proper auth headers
```

### Pattern 3: Background Monitoring

```
User sets up watch → VibeLens monitors → Auto-triggers action

Steps:
1. User wants to monitor endpoint
2. Ask: "Watch this URL and notify when X happens"
3. Use: schedule_watch(name, url, condition, action)
4. VibeLens polls endpoint in background
5. Action triggers when condition met
```

### Pattern 4: Crawler Generation (VibeCrawl)

```
User browses pages → VibeLens captures → AI generates crawler

Steps:
1. User records browsing session
2. Ask: "Generate a Scrapling spider for this site"
3. Use: generate_scrapling_spider("MySiteSpider")
4. AI creates Python code with cookies, headers
5. Code bypasses anti-bot protections
```

### Pattern 5: HAR File Analysis

```
User exports HAR → VibeLens imports → AI provides digest

Steps:
1. User exports HAR from Chrome DevTools
2. Ask: "Import and analyze this HAR file"
3. Use: import_har("/path/to/file.har")
4. AI creates session and provides summary
5. Further analysis available via other tools
```

## Prerequisites

Before using VibeLens tools:

1. **Start Bridge Server**:
   ```bash
   python -m vibeengine.mcp.server
   ```

2. **Install Chrome Extension**:
   - Load `extension/` folder in chrome://extensions/

3. **Record Traffic**:
   - Click VibeLens icon → Start Recording
   - Browse target website
   - Click Stop Recording

4. **Connect AI IDE**:
   - Configure MCP server in your IDE settings

## Example Prompts

### Analysis
```
"Analyze the API calls from my last session"
"What authentication method does this site use?"
"Find all POST requests containing 'login'"
```

### Code Generation
```
"Generate Python code to replicate this API flow"
"Create a login script using the captured requests"
"Convert these requests to curl commands"
```

### Automation
```
"Watch /api/courses and alert when slots available"
"Monitor this endpoint every 30 seconds"
"Set up auto-registration when condition met"
```

### Crawling
```
"Generate a Scrapling spider from my browsing session"
"Create crawler code that inherits my login cookies"
```

## Error Handling

If tools return errors:

1. **"Bridge server not connected"**
   - Run: `python -m vibeengine.mcp.server`

2. **"No requests captured"**
   - Start recording in Chrome Extension
   - Browse target website

3. **"AI call failed"**
   - Check `.env` for API keys
   - Verify LLM_PROVIDER and LLM_MODEL settings

## Configuration

Environment variables in `.env`:

```bash
# AI Provider
LLM_PROVIDER=dashscope  # or openai, anthropic, ollama
LLM_MODEL=qwen-plus
DASHSCOPE_API_KEY=sk-...

# Server
VIBELENS_API_URL=http://localhost:8000
```