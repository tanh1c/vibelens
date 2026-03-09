"""VibeLens CLI - Command line interface"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax

from vibeengine import __version__
from vibeengine.browser import Browser
from vibeengine.agent import Agent
from vibeengine.llm import ChatOpenAI
from vibeengine.fetchers import StealthyFetcher, DynamicFetcher
from vibeengine.network import NetworkRecorder, NetworkAnalyzer

console = Console()
app = typer.Typer(
    name="vibelens",
    help="VibeLens - AI-Powered Browser Automation & API Testing",
    add_completion=True,
)

# Server app for subcommands
server_app = typer.Typer(help="Server management")
app.add_typer(server_app, name="server")

# Sessions app for subcommands
sessions_app = typer.Typer(help="Session management")
app.add_typer(sessions_app, name="sessions")

# Requests app for subcommands
requests_app = typer.Typer(help="Request management")
app.add_typer(requests_app, name="requests")

# Blueprints app for subcommands
blueprints_app = typer.Typer(help="Blueprint management")
app.add_typer(blueprints_app, name="blueprints")


# ──────────────────────────────────────────────
# Core Commands
# ──────────────────────────────────────────────

@app.command()
def version():
    """Show version"""
    console.print(f"[bold green]VibeLens[/bold green] v{__version__}")


@app.command()
def doctor():
    """Check installation and configuration"""
    console.print(Panel.fit("[bold]VibeLens Diagnostics[/bold]"))

    # Check Python version
    py_version = sys.version_info
    console.print(f"Python: {py_version.major}.{py_version.minor}.{py_version.micro}")

    # Check dependencies
    deps = [
        ("playwright", "Playwright"),
        ("httpx", "httpx"),
        ("openai", "OpenAI"),
        ("anthropic", "Anthropic"),
        ("parsel", "Parsel"),
        ("sqlmodel", "SQLModel"),
        ("litellm", "LiteLLM"),
    ]

    table = Table(title="Dependencies")
    table.add_column("Package", style="cyan")
    table.add_column("Status", style="green")

    for import_name, display_name in deps:
        try:
            __import__(import_name)
            table.add_row(display_name, "[green]OK[/green]")
        except ImportError:
            table.add_row(display_name, "[red]Missing[/red]")

    console.print(table)

    # Check configuration
    console.print("\n[bold]Configuration:[/bold]")
    env_file = Path(".env")
    if env_file.exists():
        console.print("  .env: [green]Found[/green]")
    else:
        console.print("  .env: [yellow]Not found[/yellow]")

    # Check Playwright browsers
    try:
        import subprocess
        result = subprocess.run(
            ["playwright", "--version"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            console.print(f"  Playwright CLI: [green]{result.stdout.strip()}[/green]")
    except Exception:
        console.print("  Playwright CLI: [red]Not installed[/red]")


@app.command()
def install():
    """Install Playwright browsers"""
    console.print("[cyan]Installing Playwright browsers...[/cyan]")

    import subprocess
    result = subprocess.run(
        ["playwright", "install", "chromium"],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        console.print("[green]Browsers installed successfully[/green]")
    else:
        console.print(f"[red]Error: {result.stderr}[/red]")


# ──────────────────────────────────────────────
# Server Commands
# ──────────────────────────────────────────────

@server_app.command("start")
def server_start(
    host: str = typer.Option("localhost", "--host", "-h"),
    port: int = typer.Option(8000, "--port", "-p"),
    reload: bool = typer.Option(False, "--reload", "-r"),
):
    """Start the VibeLens Bridge Server"""
    console.print(Panel.fit(
        f"[bold green]Starting VibeLens Bridge Server[/bold green]\n"
        f"Host: {host}\n"
        f"Port: {port}\n"
        f"Reload: {reload}"
    ))

    import uvicorn

    uvicorn.run(
        "vibeengine.mcp.server:app",
        host=host,
        port=port,
        reload=reload,
    )


@server_app.command("mcp")
def server_mcp():
    """Start the VibeLens MCP Server (for AI IDEs)"""
    console.print("[cyan]Starting Vibelens MCP Server...[/cyan]")
    console.print("[dim]This server communicates via stdio with AI IDEs[/dim]")

    from vibeengine.mcp.mcp_server import main
    main()


@server_app.command("status")
def server_status(
    url: str = typer.Option("http://localhost:8000", "--url", "-u"),
):
    """Check bridge server status"""
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{url}/")
            data = response.json()

        console.print(Panel.fit(
            f"[bold green]Server Status[/bold green]\n"
            f"URL: {url}\n"
            f"Status: [green]Running[/green]\n"
            f"Requests: {data.get('requests_count', 0)}"
        ))
    except httpx.ConnectError:
        console.print(f"[red]Cannot connect to server at {url}[/red]")
        console.print("[dim]Start the server with: vibelens server start[/dim]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


# ──────────────────────────────────────────────
# Sessions Commands
# ──────────────────────────────────────────────

@sessions_app.command("list")
def sessions_list(
    limit: int = typer.Option(10, "--limit", "-l"),
    url: str = typer.Option("http://localhost:8000", "--url", "-u"),
):
    """List recording sessions"""
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{url}/sessions", params={"limit": limit})
            data = response.json()

        sessions = data.get("sessions", [])
        if not sessions:
            console.print("[yellow]No sessions found[/yellow]")
            return

        table = Table(title=f"Recording Sessions ({len(sessions)})")
        table.add_column("ID", style="cyan")
        table.add_column("Domain", style="green")
        table.add_column("Requests", style="yellow")
        table.add_column("Started", style="dim")

        for sess in sessions:
            table.add_row(
                sess.get("id", "?")[:8],
                sess.get("domain", "?"),
                str(sess.get("request_count", 0)),
                sess.get("started_at", "?")[:19] if sess.get("started_at") else "?",
            )

        console.print(table)

    except httpx.ConnectError:
        console.print(f"[red]Cannot connect to server at {url}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@sessions_app.command("show")
def sessions_show(
    session_id: str = typer.Argument(..., help="Session ID"),
    url: str = typer.Option("http://localhost:8000", "--url", "-u"),
):
    """Show session details"""
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{url}/sessions/{session_id}")
            data = response.json()

        if "error" in data:
            console.print(f"[red]{data['error']}[/red]")
            return

        console.print(Panel.fit(
            f"[bold green]Session: {data.get('id', '?')}[/bold green]\n"
            f"Domain: {data.get('domain', '?')}\n"
            f"Requests: {data.get('request_count', 0)}\n"
            f"Started: {data.get('started_at', '?')}\n"
            f"Ended: {data.get('ended_at', '?')}\n"
            f"Status: {data.get('status', '?')}"
        ))

    except httpx.ConnectError:
        console.print(f"[red]Cannot connect to server at {url}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@sessions_app.command("delete")
def sessions_delete(
    session_id: str = typer.Argument(..., help="Session ID"),
    url: str = typer.Option("http://localhost:8000", "--url", "-u"),
    force: bool = typer.Option(False, "--force", "-f"),
):
    """Delete a session"""
    if not force:
        confirm = typer.confirm(f"Delete session {session_id}?")
        if not confirm:
            console.print("[yellow]Cancelled[/yellow]")
            return

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.delete(f"{url}/sessions/{session_id}")
            data = response.json()

        if "error" in data:
            console.print(f"[red]{data['error']}[/red]")
        else:
            console.print(f"[green]Session {session_id} deleted[/green]")

    except httpx.ConnectError:
        console.print(f"[red]Cannot connect to server at {url}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


# ──────────────────────────────────────────────
# Requests Commands
# ──────────────────────────────────────────────

@requests_app.command("list")
def requests_list(
    limit: int = typer.Option(20, "--limit", "-l"),
    pattern: str = typer.Option(None, "--pattern", "-p"),
    url: str = typer.Option("http://localhost:8000", "--url", "-u"),
):
    """List captured requests"""
    try:
        with httpx.Client(timeout=10.0) as client:
            params = {"limit": limit}
            if pattern:
                params["pattern"] = pattern
            response = client.get(f"{url}/requests", params=params)
            data = response.json()

        requests = data.get("requests", [])
        if not requests:
            console.print("[yellow]No requests found[/yellow]")
            console.print("[dim]Use the Chrome Extension to capture requests[/dim]")
            return

        table = Table(title=f"Captured Requests ({len(requests)})")
        table.add_column("#", style="dim")
        table.add_column("Status", style="green")
        table.add_column("Method", style="cyan")
        table.add_column("URL", style="white")

        for i, req in enumerate(requests):
            status = req.get("status", "?")
            status_style = "green" if 200 <= status < 300 else "red" if status >= 400 else "yellow"
            table.add_row(
                str(i + 1),
                f"[{status_style}]{status}[/{status_style}]",
                req.get("method", "?"),
                req.get("url", "?")[:60],
            )

        console.print(table)

    except httpx.ConnectError:
        console.print(f"[red]Cannot connect to server at {url}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@requests_app.command("show")
def requests_show(
    index: int = typer.Argument(..., help="Request index (1-based)"),
    url: str = typer.Option("http://localhost:8000", "--url", "-u"),
):
    """Show request details"""
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{url}/requests", params={"limit": 500})
            data = response.json()

        requests = data.get("requests", [])
        idx = index - 1

        if idx < 0 or idx >= len(requests):
            console.print(f"[red]Invalid index. Use 1-{len(requests)}[/red]")
            return

        req = requests[idx]

        # Display request
        console.print(Panel.fit(
            f"[bold green]Request #{index}[/bold green]\n"
            f"URL: {req.get('url', '?')}\n"
            f"Method: {req.get('method', '?')}\n"
            f"Status: {req.get('status', '?')}"
        ))

        # Headers
        if req.get("headers"):
            console.print("\n[bold]Headers:[/bold]")
            for key, val in req["headers"].items():
                console.print(f"  {key}: {val}")

        # Request body
        if req.get("postData"):
            console.print("\n[bold]Request Body:[/bold]")
            try:
                body_json = json.loads(req["postData"])
                console.print(Syntax(json.dumps(body_json, indent=2), "json", theme="monokai"))
            except Exception:
                console.print(req["postData"][:500])

        # Response body
        if req.get("responseBody"):
            console.print("\n[bold]Response Body:[/bold]")
            try:
                body_json = json.loads(req["responseBody"])
                console.print(Syntax(json.dumps(body_json, indent=2)[:2000], "json", theme="monokai"))
            except Exception:
                console.print(req["responseBody"][:500])

    except httpx.ConnectError:
        console.print(f"[red]Cannot connect to server at {url}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@requests_app.command("clear")
def requests_clear(
    url: str = typer.Option("http://localhost:8000", "--url", "-u"),
    force: bool = typer.Option(False, "--force", "-f"),
):
    """Clear all captured requests"""
    if not force:
        confirm = typer.confirm("Clear all captured requests?")
        if not confirm:
            console.print("[yellow]Cancelled[/yellow]")
            return

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(f"{url}/clear")
            data = response.json()

        console.print(f"[green]Cleared {data.get('cleared', 0)} requests[/green]")

    except httpx.ConnectError:
        console.print(f"[red]Cannot connect to server at {url}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


# ──────────────────────────────────────────────
# HAR Commands
# ──────────────────────────────────────────────

@app.command()
def har(
    file_path: str = typer.Argument(..., help="Path to HAR file"),
    url: str = typer.Option("http://localhost:8000", "--url", "-u"),
):
    """Import a HAR file"""
    har_path = Path(file_path)

    if not har_path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        return

    console.print(f"[cyan]Importing HAR file: {file_path}[/cyan]")

    try:
        with open(har_path, "r", encoding="utf-8") as f:
            har_data = json.load(f)

        entries = har_data.get("log", {}).get("entries", [])
        console.print(f"[green]Found {len(entries)} entries in HAR file[/green]")

        # Send to server
        with httpx.Client(timeout=30.0) as client:
            # Create session
            domain = "har.import"
            for entry in entries[:1]:
                from urllib.parse import urlparse
                parsed = urlparse(entry.get("request", {}).get("url", ""))
                if parsed.netloc:
                    domain = parsed.netloc

            response = client.post(f"{url}/sessions", json={"domain": domain, "name": f"HAR Import ({domain})"})
            session_data = response.json()
            session_id = session_data.get("session_id")

            if not session_id:
                console.print("[red]Failed to create session[/red]")
                return

            # Parse and send requests
            requests = []
            for entry in entries:
                req = entry.get("request", {})
                res = entry.get("response", {})

                url_str = req.get("url", "")
                if not url_str.startswith("http"):
                    continue

                vibelens_req = {
                    "url": url_str,
                    "method": req.get("method", "GET"),
                    "headers": {h["name"]: h["value"] for h in req.get("headers", [])},
                    "responseHeaders": {h["name"]: h["value"] for h in res.get("headers", [])},
                    "postData": req.get("postData", {}).get("text", ""),
                    "responseBody": res.get("content", {}).get("text", ""),
                    "status": res.get("status", 0),
                    "mimeType": res.get("content", {}).get("mimeType", ""),
                }
                requests.append(vibelens_req)

            # Save requests
            response = client.post(f"{url}/requests", json={
                "session_id": session_id,
                "requests": requests,
            })

            console.print(f"[green]Imported {len(requests)} requests[/green]")
            console.print(f"[dim]Session ID: {session_id}[/dim]")

    except json.JSONDecodeError:
        console.print("[red]Invalid HAR file format[/red]")
    except httpx.ConnectError:
        console.print(f"[red]Cannot connect to server at {url}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


# ──────────────────────────────────────────────
# Blueprints Commands
# ──────────────────────────────────────────────

@blueprints_app.command("list")
def blueprints_list(
    url: str = typer.Option("http://localhost:8000", "--url", "-u"),
):
    """List saved blueprints"""
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{url}/blueprints")
            data = response.json()

        blueprints = data.get("blueprints", [])
        if not blueprints:
            console.print("[yellow]No blueprints found[/yellow]")
            return

        table = Table(title=f"Blueprints ({len(blueprints)})")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Domain", style="yellow")
        table.add_column("Endpoints", style="dim")

        for bp in blueprints:
            table.add_row(
                bp.get("id", "?"),
                bp.get("name", "?"),
                bp.get("domain", "?"),
                str(bp.get("endpoint_count", 0)),
            )

        console.print(table)

    except httpx.ConnectError:
        console.print(f"[red]Cannot connect to server at {url}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@blueprints_app.command("create")
def blueprints_create(
    name: str = typer.Option(..., "--name", "-n"),
    domain: str = typer.Option("", "--domain", "-d"),
    description: str = typer.Option("", "--description", "--desc"),
    url: str = typer.Option("http://localhost:8000", "--url", "-u"),
):
    """Create a blueprint from captured requests"""
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(f"{url}/blueprints", json={
                "name": name,
                "domain": domain,
                "description": description,
            })
            data = response.json()

        if "error" in data:
            console.print(f"[red]{data['error']}[/red]")
        else:
            bp = data.get("blueprint", {})
            console.print(f"[green]Blueprint '{bp.get('name')}' created[/green]")
            console.print(f"[dim]ID: {bp.get('id')}[/dim]")

    except httpx.ConnectError:
        console.print(f"[red]Cannot connect to server at {url}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


# ──────────────────────────────────────────────
# Browser Commands
# ──────────────────────────────────────────────

@app.command()
def fetch(url: str):
    """Fetch a URL using stealth fetcher"""
    console.print(f"[cyan]Fetching {url}...[/cyan]")

    async def run():
        fetcher = StealthyFetcher(headless=True)
        try:
            response = await fetcher.fetch(url)
            console.print(f"[green]Status: {response.status}[/green]")
            console.print(f"[blue]Content length: {len(response.content)} bytes[/blue]")
            console.print(response.content[:500])
        finally:
            await fetcher.close()

    asyncio.run(run())


@app.command()
def stealth(
    url: str,
    solve_cloudflare: bool = typer.Option(False, "--cloudflare", "-c"),
):
    """Fetch URL with stealth mode"""
    console.print(f"[cyan]Fetching {url} with stealth mode...[/cyan]")

    async def run():
        fetcher = StealthyFetcher(
            headless=True,
            solve_cloudflare=solve_cloudflare,
        )
        try:
            response = await fetcher.fetch(url)
            console.print(f"[green]Status: {response.status}[/green]")
            console.print(response.content[:1000])
        finally:
            await fetcher.close()

    asyncio.run(run())


@app.command()
def shell(
    url: str = typer.Option("https://example.com", "--url", "-u"),
):
    """Start interactive browser shell"""
    console.print(Panel.fit(
        "[bold]VibeLens Interactive Shell[/bold]\n"
        f"Starting browser at {url}..."
    ))

    async def run():
        browser = Browser(headless=False)
        await browser.start()
        await browser.goto(url)

        console.print(f"[green]Browser opened at {url}[/green]")
        console.print("Commands: goto, screenshot, html, title, url, click, type, exit")

        try:
            while True:
                command = await asyncio.get_event_loop().run_in_executor(
                    None, input, "vibelens> "
                )
                command = command.strip()

                if not command:
                    continue

                if command in ["exit", "quit", "q"]:
                    break

                parts = command.split(maxsplit=1)
                cmd = parts[0]
                args = parts[1] if len(parts) > 1 else ""

                if cmd == "goto":
                    await browser.goto(args)
                    console.print(f"[green]Navigated to {args}[/green]")
                elif cmd == "screenshot":
                    path = args or "screenshot.png"
                    await browser.screenshot(path)
                    console.print(f"[green]Screenshot saved to {path}[/green]")
                elif cmd == "html":
                    html = await browser.get_html()
                    console.print(html[:500])
                elif cmd == "title":
                    title = await browser.get_title()
                    console.print(f"Title: {title}")
                elif cmd == "url":
                    current_url = await browser.get_url()
                    console.print(f"URL: {current_url}")
                elif cmd == "click":
                    await browser.click(args)
                    console.print(f"[green]Clicked: {args}[/green]")
                elif cmd == "type":
                    parts2 = args.split(maxsplit=1)
                    if len(parts2) == 2:
                        await browser.type(parts2[0], parts2[1])
                        console.print(f"[green]Typed into {parts2[0]}[/green]")
                    else:
                        console.print("[red]Usage: type <selector> <text>[/red]")
                else:
                    console.print(f"[red]Unknown command: {cmd}[/red]")
                    console.print("Commands: goto, screenshot, html, title, url, click, type, exit")

        except KeyboardInterrupt:
            pass
        finally:
            await browser.close()
        console.print("[yellow]Browser closed[/yellow]")

    asyncio.run(run())


@app.command()
def extract(
    url: str,
    output: str,
    css: Optional[str] = typer.Option(None, "--css", "-c"),
):
    """Extract content from URL"""
    console.print(f"[cyan]Extracting from {url}...[/cyan]")

    async def run():
        fetcher = DynamicFetcher(headless=True)
        try:
            response = await fetcher.fetch(url)

            from vibeengine.parser import Selector
            selector = Selector(response.content, base_url=url)

            if css:
                elements = selector.css(css)
                content = "\n".join([el.text for el in elements])
            else:
                elements = selector.css("body")
                content = elements[0].text if elements else response.content

            Path(output).write_text(content, encoding="utf-8")
            console.print(f"[green]Saved to {output}[/green]")

        finally:
            await fetcher.close()

    asyncio.run(run())


@app.command()
def analyze(
    url: str,
    prompt: Optional[str] = typer.Option(None, "--prompt", "-p"),
):
    """Analyze API traffic from URL"""
    console.print(f"[cyan]Analyzing traffic from {url}...[/cyan]")

    async def run():
        browser = Browser()
        recorder = NetworkRecorder()

        await browser.start()
        page = await browser.new_page()
        await recorder.start(page)

        await page.goto(url)
        await asyncio.sleep(2)  # Wait for traffic

        await recorder.stop()

        entries = recorder.get_entries()
        console.print(f"[cyan]Captured {len(entries)} requests[/cyan]")

        analyzer = NetworkAnalyzer()
        analysis = await analyzer.analyze_api(entries, prompt=prompt)

        console.print(Panel(analysis, title="AI Analysis"))
        await browser.close()

    asyncio.run(run())


@app.command()
def run(
    task: str,
    headless: bool = typer.Option(False, "--headless", "-H"),
):
    """Run AI agent task"""
    console.print(f"[cyan]Running task: {task}[/cyan]")

    async def run_agent():
        browser = Browser(headless=headless)
        agent = Agent(task=task, llm=ChatOpenAI(), browser=browser)

        history = await agent.run()

        console.print(Panel.fit(
            f"[green]Task completed in {len(history.actions)} steps[/green]"
        ))

        if history.errors:
            console.print(f"[yellow]Errors: {len(history.errors)}[/yellow]")

    asyncio.run(run_agent())


# ──────────────────────────────────────────────
# Security Commands (Bug Bounty / Security Research)
# ──────────────────────────────────────────────

security_app = typer.Typer(help="Security testing tools (Bug Bounty)")
app.add_typer(security_app, name="security")


@security_app.command("scan")
def security_scan(
    tests: str = typer.Option("all", "--tests", "-t"),
    limit: int = typer.Option(20, "--limit", "-l"),
    server_url: str = typer.Option("http://localhost:8000", "--server", "-s"),
):
    """Scan captured requests for vulnerabilities (IDOR, XSS, SQLi, Headers)"""
    console.print(Panel.fit(
        "[bold red]🔒 VibeLens Security Scanner[/bold red]\n"
        f"Tests: {tests} | Limit: {limit}"
    ))

    async def run():
        from vibeengine.security import SecurityScanner

        # Get requests from server
        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{server_url}/requests/filtered?limit={limit}")
            data = response.json()

        requests = data.get("requests", [])
        if not requests:
            console.print("[yellow]No requests found. Capture some first.[/yellow]")
            return

        console.print(f"[cyan]Scanning {len(requests)} requests...[/cyan]")

        test_list = ["idor", "headers", "fuzz"] if tests == "all" else [tests]

        scanner = SecurityScanner()
        try:
            result = await scanner.scan_captured_endpoints(requests, test_list)

            # Display results
            console.print(f"\n[green]Scan Complete![/green]")
            console.print(f"  Endpoints tested: {result.endpoints_tested}")
            console.print(f"  Duration: {result.scan_duration:.2f}s")
            console.print(f"  Findings: {len(result.findings)}")

            if result.findings:
                # Create findings table
                table = Table(title="Vulnerability Findings")
                table.add_column("Severity", style="bold")
                table.add_column("Title")
                table.add_column("Endpoint")

                for finding in result.findings:
                    sev_color = {
                        "critical": "red",
                        "high": "orange1",
                        "medium": "yellow",
                        "low": "green",
                        "info": "blue",
                    }.get(finding.severity.value, "white")

                    table.add_row(
                        f"[{sev_color}]{finding.severity.value.upper()}[/{sev_color}]",
                        finding.title,
                        finding.endpoint[:50],
                    )

                console.print(table)
            else:
                console.print("[green]✅ No vulnerabilities found![/green]")

        finally:
            await scanner.close()

    asyncio.run(run())


@security_app.command("idor")
def test_idor(
    request_index: int = typer.Argument(..., help="Request index (1-based)"),
    server_url: str = typer.Option("http://localhost:8000", "--server", "-s"),
):
    """Test IDOR vulnerability on a specific request"""
    console.print(f"[cyan]Testing IDOR on request #{request_index}...[/cyan]")

    async def run():
        from vibeengine.security import IDORTester
        import httpx

        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{server_url}/requests?limit=500")
            data = response.json()

        requests = data.get("requests", [])
        idx = request_index - 1

        if idx < 0 or idx >= len(requests):
            console.print(f"[red]Invalid index. Use 1-{len(requests)}[/red]")
            return

        req = requests[idx]
        url = req.get("url", "")

        # Extract IDOR params
        idor_params = IDORTester.extract_ids_from_url(url)

        if not idor_params:
            console.print("[yellow]No IDOR parameters found in this request.[/yellow]")
            return

        console.print(f"[green]Found IDOR parameters:[/green]")
        for param_name, value in idor_params:
            console.print(f"  • {param_name}: {value}")
            variants = IDORTester.generate_idor_variants(value)
            console.print(f"    Test with: {variants[:5]}")

    asyncio.run(run())


@security_app.command("fuzz")
def fuzz_params(
    request_index: int = typer.Argument(..., help="Request index (1-based)"),
    fuzz_type: str = typer.Option("all", "--type", "-t"),
    server_url: str = typer.Option("http://localhost:8000", "--server", "-s"),
):
    """Fuzz parameters on a specific request"""
    console.print(f"[cyan]Fuzzing request #{request_index} ({fuzz_type})...[/cyan]")

    async def run():
        from vibeengine.security import ParameterFuzzer

        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{server_url}/requests?limit=500")
            data = response.json()

        requests = data.get("requests", [])
        idx = request_index - 1

        if idx < 0 or idx >= len(requests):
            console.print(f"[red]Invalid index. Use 1-{len(requests)}[/red]")
            return

        req = requests[idx]
        params = ParameterFuzzer.extract_parameters(req)

        if not params:
            console.print("[yellow]No parameters found in this request.[/yellow]")
            return

        console.print(f"[green]Parameters to fuzz:[/green]")
        for param_name, values in params.items():
            console.print(f"  • {param_name}: {values[0] if values else '(empty)'}")

        console.print(f"\n[green]Payloads available:[/green]")
        for ptype, payloads in ParameterFuzzer.FUZZ_PAYLOADS.items():
            console.print(f"  • {ptype}: {len(payloads)} payloads")

    asyncio.run(run())


@security_app.command("headers")
def check_headers(
    url: Optional[str] = typer.Argument(None, help="URL to check"),
    server_url: str = typer.Option("http://localhost:8000", "--server", "-s"),
):
    """Check security headers of a URL"""
    console.print(f"[cyan]Checking security headers...[/cyan]")

    async def run():
        from vibeengine.security import SecurityHeaderAnalyzer
        import httpx

        if url:
            urls = [url]
        else:
            # Use captured requests
            with httpx.Client(timeout=10.0) as client:
                response = client.get(f"{server_url}/requests/filtered?limit=10")
                data = response.json()
            requests = data.get("requests", [])
            urls = [r.get("url", "") for r in requests if r.get("url")]

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            for test_url in urls[:5]:
                try:
                    response = await client.get(test_url)
                    findings = SecurityHeaderAnalyzer.analyze_headers(dict(response.headers))

                    console.print(f"\n[bold]{test_url}[/bold]")
                    if findings:
                        for f in findings:
                            sev_color = {
                                "critical": "red",
                                "high": "orange1",
                                "medium": "yellow",
                                "low": "green",
                                "info": "blue",
                            }.get(f.severity.value, "white")
                            console.print(f"  [{sev_color}]•[/{sev_color}] {f.title}")
                    else:
                        console.print("  [green]✅ All security headers present[/green]")

                except Exception as e:
                    console.print(f"  [red]Error: {e}[/red]")

    asyncio.run(run())


@security_app.command("auth-bypass")
def test_auth_bypass(
    request_index: int = typer.Argument(..., help="Request index (1-based)"),
    server_url: str = typer.Option("http://localhost:8000", "--server", "-s"),
):
    """Test authentication bypass techniques"""
    console.print(f"[cyan]Testing auth bypass on request #{request_index}...[/cyan]")

    async def run():
        from vibeengine.security import AuthBypassTester, SecurityScanner

        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{server_url}/requests?limit=500")
            data = response.json()

        requests = data.get("requests", [])
        idx = request_index - 1

        if idx < 0 or idx >= len(requests):
            console.print(f"[red]Invalid index. Use 1-{len(requests)}[/red]")
            return

        req = requests[idx]
        url = req.get("url", "")
        headers = req.get("headers", {})

        console.print(f"[green]Testing {len(AuthBypassTester.BYPASS_TECHNIQUES)} bypass techniques...[/green]")

        scanner = SecurityScanner()
        try:
            result = await scanner.auth_bypass_scan(url, headers)

            if result.findings:
                console.print(f"[red]Found {len(result.findings)} potential bypasses![/red]")
                for f in result.findings:
                    console.print(f"  • {f.title}")
                    console.print(f"    Evidence: {f.evidence[:100]}")
            else:
                console.print("[green]✅ No bypass found[/green]")

        finally:
            await scanner.close()

    asyncio.run(run())


@security_app.command("hexstrike")
def hexstrike_status():
    """Check HexStrike AI server status"""
    console.print("[cyan]Checking HexStrike AI connection...[/cyan]")

    async def run():
        from vibeengine.security import HexStrikeBridge

        bridge = HexStrikeBridge()
        try:
            available = await bridge.is_available()

            if available:
                console.print(Panel.fit(
                    "[bold green]HexStrike AI: Connected[/bold green]\n"
                    f"URL: {bridge.server_url}\n\n"
                    "Available Tools:\n"
                    "  🔍 Network: nmap, rustscan, masscan\n"
                    "  🌐 Web: nuclei, sqlmap, ffuf, gobuster\n"
                    "  🔐 Auth: hydra, john, hashcat\n"
                    "  ☁️ Cloud: prowler, scout-suite, trivy"
                ))
            else:
                console.print(Panel.fit(
                    "[bold red]HexStrike AI: Not Available[/bold red]\n"
                    f"URL: {bridge.server_url}\n\n"
                    "How to start:\n"
                    "  1. cd hexstrike-ai\n"
                    "  2. pip install -r requirements.txt\n"
                    "  3. python hexstrike_server.py"
                ))

        finally:
            await bridge.close()

    asyncio.run(run())


@security_app.command("hexstrike-scan")
def hexstrike_scan(
    target: str = typer.Argument(..., help="Target URL or IP"),
    scan_type: str = typer.Option("quick", "--type", "-t"),
):
    """Run HexStrike AI advanced scan"""
    console.print(Panel.fit(
        f"[bold red]🚀 HexStrike AI Scan[/bold red]\n"
        f"Target: {target}\n"
        f"Type: {scan_type}"
    ))

    async def run():
        from vibeengine.security import HexStrikeBridge

        bridge = HexStrikeBridge()
        try:
            available = await bridge.is_available()
            if not available:
                console.print("[red]HexStrike server not available. Run 'vibelens security hexstrike' for help.[/red]")
                return

            console.print("[cyan]Running scan...[/cyan]")

            if scan_type == "quick":
                result = await bridge.nuclei_scan(target)
            elif scan_type == "full":
                result = await bridge.analyze_target(target)
            else:
                result = await bridge.nuclei_scan(target)

            console.print(Panel(
                json.dumps(result, indent=2)[:2000],
                title="Scan Results"
            ))

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
        finally:
            await bridge.close()

    asyncio.run(run())


def main():
    """Main entry point"""
    app()


if __name__ == "__main__":
    main()