"""Basic example - Simple browser automation"""

import asyncio

from vibeengine import Browser, Agent
from vibeengine.llm import ChatOpenAI


async def main():
    # Create browser
    browser = Browser(headless=False)

    # Create agent
    agent = Agent(
        task="Open Google and search for 'VibeLens AI'",
        llm=ChatOpenAI(model="gpt-4"),
        browser=browser,
    )

    # Run agent
    history = await agent.run()

    print(f"Task completed in {len(history.actions)} steps")
    print(f"Visited URLs: {history.urls}")
    print(f"Extracted content: {history.extracted_content}")

    # Close browser
    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
