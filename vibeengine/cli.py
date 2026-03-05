"""VibeLens CLI - Command line interface"""

import asyncio
import logging
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from vibeengine import __version__
from vibeengine.browser import Browser
from vibeengine.agent import Agent
from vibeengine.llm import ChatOpenAI
from vibeengine.fetchers import StealthyFetcher, DynamicFetcher
from vibeengine.network import NetworkRecorder, NetworkAnalyzer

console = Console()
app = typer.Typer(help="VibeLens - AI-Powered Browser Automation & API Testing")


@app.command()
def version():
    """Show version"""
    console.print(f"VibeLens v{__version__}")


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
def stealth(url: str, solve_cloudflare: bool = False):
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
def shell(url: str = "https://example.com"):
    """Start interactive shell"""
    console.print(Panel.fit(
        "[bold]VibeLens Interactive Shell[/bold]\n"
        f"Starting browser at {url}..."
    ))

    async def run():
        browser = Browser(headless=False)
        await browser.start()
        await browser.goto(url)

        console.print(f"[green]Browser opened at {url}[/green]")
        console.print("Press Ctrl+C to exit")

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
                    url = await browser.get_url()
                    console.print(f"URL: {url}")
                else:
                    console.print(f"[red]Unknown command: {cmd}[/red]")
                    console.print("Available: goto, screenshot, html, title, url")

        except KeyboardInterrupt:
            pass
        finally:
            await browser.close()
        console.print("[yellow]Browser closed[/yellow]")

    asyncio.run(run())


@app.command()
def run(task: str):
    """Run agent task"""
    console.print(f"[cyan]Running task: {task}[/cyan]")

    async def run_agent():
        agent = Agent(task=task, llm=ChatOpenAI())
        history = await agent.run()

        console.print(Panel.fit(
            f"[green]Task completed in {len(history.actions)} steps[/green]"
        ))

    asyncio.run(run_agent())


@app.command()
def extract(url: str, output: str, css: str = None):
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
                # Get body content
                elements = selector.css("body")
                content = elements[0].text if elements else response.content

            # Write to file
            Path(output).write_text(content, encoding="utf-8")
            console.print(f"[green]Saved to {output}[/green]")

        finally:
            await fetcher.close()

    asyncio.run(run())


@app.command()
def analyze(url: str):
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

        # Analyze with AI
        entries = recorder.get_entries()
        console.print(f"[cyan]Captured {len(entries)} requests[/cyan]")

        analyzer = NetworkAnalyzer()
        analysis = await analyzer.analyze_api(entries)

        console.print(Panel(analysis, title="AI Analysis"))
        await browser.close()

    asyncio.run(run())


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


def main():
    """Main entry point"""
    app()


if __name__ == "__main__":
    main()
