# 🔍 VibeLens

**AI-Powered Network Tracker & MCP Security Engine**

VibeLens bridges your browser, a local server, and your AI assistant (via Model Context Protocol) to autonomously capture, analyze, and replicate network traffic. Gone are the days of manually copying cURL commands from the DevTools Network tab. VibeLens lets your AI "see" exactly what your browser sees, and now with **HexStrike AI** and **Scrapling**, it can execute 156+ security tools and auto-generate robust parsers natively.

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| **[USECASES.md](docs/USECASES.md)** | Hướng dẫn chi tiết 8 use cases (Vietnamese) |
| **[SECURITY_GUIDE.md](docs/SECURITY_GUIDE.md)** | Bug Bounty & Security Research Guide |
| **[scripts/HEXSTRIKE_UPDATE_GUIDE.md](scripts/HEXSTRIKE_UPDATE_GUIDE.md)** | Guide to update HexStrike integration |
| **[vibeengine/skills/SKILL.md](vibeengine/skills/SKILL.md)** | Skill file for AI assistants |

---

## 🌟 Version Status

| Feature | Status | Description |
|---------|--------|-------------|
| **Core Capture** | ✅ Released | XHR/Fetch, multi-domain SSO, cookies, payloads |
| **Bridge Server** | ✅ Released | FastAPI server with SQLite persistence |
| **MCP Tools** | ✅ Released | 20+ tools for AI-powered analysis & security |
| **HAR Import** | ✅ Released | Import HAR files with AI Digest |
| **Scrapling Auto-RAG** | ✅ Released | Auto-generate crawler, auto-pull latest Scrapling docs (RAG) |
| **Dashboard UI** | ✅ Released | Web app for session management |
| **HexStrike 100% Unlock** | ✅ Released | Full access to 156 endpoints (90+ tools, AI Payload, CTF, etc.) |
| **Process/File Mgmt** | ✅ Released | Full process and file operations over MCP |
| **Error Recovery** | 🚧 Planned | Tab crash, network disconnect handling |

---

## 🏗️ The VibeLens Ecosystem

1. **The Observer (Chrome Extension):** Silently monitors XHR/Fetch requests, multi-domain SSO redirect chains, cookies, and payloads.
2. **The Bridge (FastAPI):** A local HTTP server that receives captured data from the extension and manages state, applying sensitive data masking on the fly.
3. **The Brain (MCP Server):** Exposes the captured network context and powerful execution tools to MCP-compatible AI IDEs (Claude Code, Cursor, Antigravity, RooCode).
4. **VibeCrawl (Scrapling):** Auto-generates crawler code from captured requests. It uses a built-in Auto-RAG mechanism to pull the latest syntax direct from Scrapling docs.
5. **The Shield (HexStrike AI):** A deeply integrated security engine providing 150+ capabilities (Nmap, SQLMap, Nuclei, CTF solvers, Threat Intel) over the MCP link.

---

## 🎯 Use Cases at a Glance

| Use Case | What You Can Do |
|----------|-----------------|
| **API Reverse Engineering** | Understand undocumented APIs by capturing browser traffic |
| **Auth Flow Analysis** | Analyze login flows, SSO redirects, token locations |
| **Crawler Generation (VibeCrawl)** | Generate 100% accurate Scrapling spiders using live browser data & Auto-RAG docs |
| **Background Automation** | Watch endpoints and auto-trigger actions |
| **Security Scanning** | Run AI-driven Smart Scans (HexStrike) combining multiple tools automatically |
| **CTF / Vuln Intel** | Solve crypto challenges, analyze binaries, or pull CVE intelligence |
| **Bug Bounty Hunting** | IDOR, XSS, SQLi testing on captured endpoints |

📖 **See [USECASES.md](docs/USECASES.md) for detailed guides.**
📖 **See [SECURITY_GUIDE.md](docs/SECURITY_GUIDE.md) for bug bounty workflow.**

---

## 🚀 Quick Install

### 1. Install the Core Package
```bash
# Clone the repository
git clone https://github.com/tanh1c/vibelens.git
cd vibelens

# Create a virtual environment
python -m venv .venv
# Activate: (Windows: .venv\Scripts\activate | Mac/Linux: source .venv/bin/activate)

# Install VibeLens
pip install -e .
```

### 2. Install the Chrome Extension
1. Open Chrome and navigate to `chrome://extensions/`.
2. Enable **Developer Mode**.
3. Click **Load unpacked** and select the `vibelens/extension/` folder.
4. Pin the VibeLens icon.

### 3. (Optional) Run HexStrike Server
For the advanced security tools, you need the HexStrike AI engine running.
```bash
cd hexstrike-ai
pip install -r requirements.txt
python hexstrike_server.py
```
*(Note: Docker or WSL is highly recommended for full Linux-only tool compatibility in HexStrike).*

---

## ⚙️ How to Use (The Workflow)

### Step 1: Start the Bridge Server
```bash
cd vibelens
python -m vibeengine.mcp.server
```

### Step 2: Record Traffic
1. Click the VibeLens extension icon and hit **Start Recording**.
2. Perform your actions (e.g., login, browse). VibeLens captures background requests.

### Step 3: Connect your AI (IDE)
Connect the VibeLens MCP Server to your preferred IDE.

**For Claude Code CLI:**
```bash
claude mcp add vibelens -- /absolute/path/to/your/.venv/bin/python -m vibeengine.mcp.mcp_server
```

**For Cursor / RooCode / Cline (`mcp_config.json`):**
```json
{
  "mcpServers": {
    "vibelens": {
      "command": "path/to/vibelens/.venv/Scripts/python.exe",
      "args": ["-m", "vibeengine.mcp.mcp_server"]
    }
  }
}
```

### Step 4: Prompt your AI
Ask your AI assistant to analyze the flow:
> *"Generate a Scrapling spider from my latest VibeLens captured requests."*

The AI will dynamically inject the latest Scrapling Documentation (via VibeCrawl RAG) and output perfect syntax immediately.

---

## 🖥️ Dashboard UI
Access the Web Dashboard at: `http://localhost:8000/dashboard`

**Features:**
- Session Management grouped by domain.
- Request Inspector with detailed Headers/Payload views.
- **Smart Tracking Filter** (Hybrid 3-Layer Filter, Brave EasyList engine) to cleanly separate APIs from static/junk resources.

---

## 🛡️ HexStrike: 100% Unlock Integration

VibeLens is fully hooked into the HexStrike AI Backend, granting your IDE access to exactly **156 advanced endpoints**. 

VibeLens avoids static "composite hooks". Instead, the MCP server acts as a Deep Bridge:
- `hexstrike_tool()`: Run any of the 90+ security tools (nmap, sqli, nuclei, etc).
- `hexstrike_smart_scan()`: Let the HexStrike intelligence engine dynamically pick tools.
- `hexstrike_workflow()`: Trigger specific bug bounty workflows (recon, attack).
- Advanced capabilities including **CTF solvers**, **AI Payload Generators**, and **Process Management**.

*Whenever HexStrike updates, run the automatic extraction script to update the VibeLens bridge:*
```bash
python scripts/extract_hexstrike_endpoints.py --compare --codegen
```

---

## 🕸️ VibeCrawl: Scrapling Auto-RAG

VibeLens solves AI code generation hallucination with **VibeCrawl**.
When you ask the AI to generate a `Scrapling` crawler:
1. VibeLens auto-pulls the absolute latest `Scrapling` source from GitHub.
2. VibeLens dynamically reads the latest Markdown usage docs from the Repo.
3. VibeLens injects this accurate documentation right into the AI prompt along with your browser's captured auth cookies/headers.

**Result:** Zero hallucinations. The AI always uses the correct, most recent syntax for the framework.

---

## 🔒 Security & Privacy

VibeLens runs **locally** on your machine. 
- Captured data is sent to your local Bridge Server (`localhost:8000`).
- The MCP Server includes a **Sensitive Data Masking Engine** that automatically redacts passwords, tokens, and authorization headers before sending context to the AI cloud `toggle_masking(enabled=True)`.

---

## 📄 License
MIT License. See `LICENSE` for more information.
