# 🔍 VibeLens

**AI-Powered Network Tracker & MCP Server**

VibeLens bridges your browser, a local server, and your AI assistant (via Model Context Protocol) to autonomously capture, analyze, and replicate network traffic. Gone are the days of manually copying cURL commands from the DevTools Network tab. VibeLens lets your AI "see" exactly what your browser sees.

---

## 🌟 The VibeLens Ecosystem

1. **The Observer (Chrome Extension):** Silently monitors XHR/Fetch requests, multi-domain SSO redirect chains, cookies, and payloads.
2. **The Bridge (FastAPI):** A local HTTP server that receives captured data from the extension and manages state, applying sensitive data masking on the fly.
3. **The Brain (MCP Server):** Exposes the captured network context and powerful execution tools to MCP-compatible AI IDEs (Claude Code, Cursor, Antigravity, RooCode).

---

## 🚀 Quick Install

### 1. Install the Core Package
```bash
# Clone the repository
git clone https://github.com/tanh1c/vibelens.git
cd vibelens

# Create a virtual environment
python -m venv .venv

# Activate it
# Windows: .venv\Scripts\activate
# Mac/Linux: source .venv/bin/activate

# Install VibeLens
pip install -e .
```

### 2. Install the Chrome Extension
1. Open Chrome and navigate to `chrome://extensions/`.
2. Enable **Developer Mode** (top right corner).
3. Click **Load unpacked** and select the `vibelens/extension/` folder from this repository.
4. Pin the VibeLens icon to your toolbar.

---

## ⚙️ How to Use (The Workflow)

### Step 1: Start the Bridge Server
Keep this running in a terminal. It listens for data from the Chrome Extension.
```bash
python -m vibeengine.mcp.server
```

### Step 2: Record Traffic
1. Open the target website (e.g., an e-commerce site, your university LMS, etc.).
2. Click the VibeLens extension icon and hit **Start Recording**.
3. Perform your actions (e.g., login, add to cart). VibeLens will capture everything in the background.

### Step 3: Connect your AI (IDE)
Connect the VibeLens MCP Server to your preferred IDE.

**For Claude Code CLI:**
```bash
claude mcp add vibelens -- /absolute/path/to/your/.venv/bin/python -m vibeengine.mcp.mcp_server
```

**For Cursor / RooCode / Cline:**
Go to your MCP Settings or `mcp_config.json` and add the following configuration:

```json
{
  "mcpServers": {
    "vibelens": {
      "command": "path/to/vibelens/.venv/Scripts/python.exe",
      "args": [
        "-m",
        "vibeengine.mcp.mcp_server"
      ]
    }
  }
}
```

### Step 4: Prompt your AI
Ask your AI assistant to analyze the flow. For example:
> *"I just recorded myself logging into the LMS. Use the MCP tools to read the captured requests, find the authentication cookies and the login API endpoint, and write a Python script using `httpx` to automatically log in."*

The AI will autonomously use tools like `get_auth_info()`, `find_requests_by_pattern()`, and `execute_http_request()` to reverse-engineer the API and generate the code for you!

---

## 🛠️ MCP Tools Provided to AI

| Tool | Description |
|---|---|
| `get_captured_requests(limit)` | Retrieve a list of captured network requests. |
| `get_request_detail(index)` | View the full headers, payload, and response body of a specific request. |
| `get_auth_info()` | Analyze complex authentication flows (Cookies, Tracked Domains, Set-Cookie headers, Redirect Chains). |
| `find_requests_by_pattern(pattern)` | Search for specific API endpoints or HTTP methods. |
| `execute_http_request(url, method, headers, body)` | Allow the AI to actually execute an HTTP request to test the API directly from the IDE. |

---

## 🔒 Security & Privacy

VibeLens is designed to run **locally** on your machine. 
- Captured data is sent to your local Bridge Server (`localhost:8000`).
- The MCP Server includes a **Sensitive Data Masking Engine** that automatically redacts passwords, credit card numbers, and authorization headers before sending context to the AI (this can be toggled via `toggle_masking()`).

---

## 📄 License

MIT License. See `LICENSE` for more information.
