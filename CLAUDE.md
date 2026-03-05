# VibeLens CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

VibeLens is an AI-Powered Browser Automation & API Testing Platform with network capture capabilities.

## Architecture

- **Browser Controller**: Playwright-based browser automation
- **Agent**: LLM-driven automation (GPT-4, Claude, Ollama)
- **Network Capture**: HTTP/HTTPS request capture via Chrome DevTools Protocol
- **MCP Server**: FastAPI server for AI integration

## Key Commands

```bash
# Install dependencies
pip install -e .

# Run MCP Server
python -m vibeengine.mcp.server

# Run CLI
vibelens --help

# Run examples
python examples/basic.py
python examples/api_analysis.py
```

## MCP Server Endpoints

- `POST /analyze` - Analyze captured requests with AI
- `POST /generate` - Generate code from requests
- `GET /requests` - Get captured requests
- `POST /clear` - Clear requests

## Development

- Use Python 3.11+
- Follow PEP 8 style
- Use type hints
- Run tests with pytest

## Extension

The Chrome extension is in `extension/` folder. Load it in Chrome:
1. Go to chrome://extensions/
2. Enable Developer mode
3. Load unpacked → select extension/ folder
