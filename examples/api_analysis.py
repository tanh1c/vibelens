"""API Analysis example - Capture and analyze API traffic"""

import asyncio

from vibeengine import Browser
from vibeengine.network import NetworkRecorder, NetworkAnalyzer
from vibeengine.llm import ChatOpenAI


async def main():
    """Example: Capture and analyze API traffic"""

    # Start browser with network recording
    browser = Browser()
    recorder = NetworkRecorder()

    await browser.start()

    # Get page and start recording
    page = await browser.new_page()
    await recorder.start(page)

    # Navigate to a website that makes API calls
    # Using JSONPlaceholder as a simple example
    print("Navigating to example API...")
    await page.goto("https://jsonplaceholder.typicode.com/posts")
    await page.goto("https://jsonplaceholder.typicode.com/users")
    await asyncio.sleep(1)

    # Stop recording
    await recorder.stop()

    # Get captured requests
    entries = recorder.get_entries()
    print(f"Captured {len(entries)} requests")

    # Analyze with AI
    analyzer = NetworkAnalyzer(llm=ChatOpenAI())

    print("\n=== Analyzing API traffic ===")
    analysis = await analyzer.analyze_api(entries)
    print(analysis)

    # Generate Postman collection
    print("\n=== Generating Postman Collection ===")
    collection = await analyzer.generate_postman_collection(entries, "VibeLens Demo")
    import json
    print(json.dumps(collection, indent=2)[:1000])

    # Export HAR
    print("\n=== Exporting HAR ===")
    recorder.export_har("network.har")
    print("Exported to network.har")

    # Cleanup
    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
