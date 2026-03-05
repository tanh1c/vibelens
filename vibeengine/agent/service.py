"""Agent service - LLM-driven browser automation (browser-use style)"""

import asyncio
import json
import logging
from typing import Any, Literal

from vibeengine.browser import Browser
from vibeengine.llm import BaseLLM, ChatOpenAI
from vibeengine.agent.views import AgentConfig, AgentHistory, ActionResult

logger = logging.getLogger(__name__)


class Agent:
    """
    LLM-driven browser automation agent.

    Inspired by browser-use agent architecture.
    """

    def __init__(
        self,
        task: str,
        llm: BaseLLM | None = None,
        browser: Browser | None = None,
        max_steps: int = 100,
        max_actions_per_step: int = 3,
        max_failures: int = 3,
        use_vision: bool = True,
        use_thinking: bool = True,
        **kwargs: Any,
    ):
        self.task = task
        self.llm = llm or ChatOpenAI()
        self.browser = browser or Browser()
        self.max_steps = max_steps
        self.max_actions_per_step = max_actions_per_step
        self.max_failures = max_failures
        self.use_vision = use_vision
        self.use_thinking = use_thinking
        self.kwargs = kwargs

        self.history = AgentHistory()
        self.current_step = 0
        self.failure_count = 0

        # System prompt for the agent
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        """Build system prompt for the agent"""
        return """You are a browser automation agent. Your task is to control a web browser to complete user tasks.

Available actions:
- navigate: Navigate to a URL
- click: Click an element by index
- input: Input text into an element by index
- scroll: Scroll the page (up/down)
- wait: Wait for a specific time
- extract: Extract content from the page using CSS selector or text
- screenshot: Take a screenshot
- done: Mark the task as complete
- error: Report an error

When you need to interact with the page, first use 'state' action to get the current page state and clickable elements.

Always respond in JSON format:
{"action": "action_name", "params": {"key": "value"}}

Example:
{"action": "navigate", "params": {"url": "https://example.com"}}
{"action": "click", "params": {"index": 5}}
{"action": "done", "params": {"result": "Task completed successfully"}}
"""

    async def run(self) -> AgentHistory:
        """Run the agent to complete the task"""
        logger.info(f"Starting agent task: {self.task}")

        try:
            # Start browser if not started
            if not self.browser._browser:
                await self.browser.start()

            # Add initial URL to history
            self.history.add_url(self.browser.page.url)

            # Main loop
            while self.current_step < self.max_steps:
                self.current_step += 1
                logger.info(f"Step {self.current_step}/{self.max_steps}")

                try:
                    # Get current page state
                    page_state = await self._get_page_state()

                    # Build messages for LLM
                    messages = self._build_messages(page_state)

                    # Get LLM response
                    response = await self.llm.chat(messages)

                    # Parse and execute action
                    result = await self._execute_action(response)

                    # Check if done
                    if result.is_done:
                        logger.info("Task completed successfully")
                        break

                    # Check for errors
                    if result.error:
                        self.failure_count += 1
                        self.history.add_error(result.error)
                        logger.warning(f"Action error: {result.error}")

                        if self.failure_count >= self.max_failures:
                            logger.error("Max failures reached")
                            break
                    else:
                        self.failure_count = 0
                        self.history.add_error(None)

                except Exception as e:
                    logger.error(f"Step error: {e}")
                    self.failure_count += 1
                    self.history.add_error(str(e))

                    if self.failure_count >= self.max_failures:
                        break

                    await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Agent error: {e}")
            self.history.add_error(str(e))

        finally:
            logger.info(f"Agent finished. Steps: {self.current_step}")

        return self.history

    async def _get_page_state(self) -> dict[str, Any]:
        """Get current page state for LLM context"""
        try:
            url = await self.browser.get_url()
            title = await self.browser.get_title()
            html = await self.browser.get_html()

            # Get clickable elements
            elements = await self.browser.get_clickable_elements()

            # Take screenshot if vision enabled
            screenshot = None
            if self.use_vision:
                screenshot = await self.browser.screenshot()
                if isinstance(screenshot, bytes):
                    import base64
                    screenshot = base64.b64encode(screenshot).decode()

            return {
                "url": url,
                "title": title,
                "html": html[:5000] if html else "",  # Limit HTML length
                "elements": [
                    {
                        "index": el.index,
                        "tag": el.tag,
                        "text": el.text,
                        "attributes": el.attributes,
                    }
                    for el in elements[:20]  # Limit elements
                ],
                "screenshot": screenshot,
            }
        except Exception as e:
            logger.error(f"Error getting page state: {e}")
            return {"error": str(e)}

    def _build_messages(self, page_state: dict[str, Any]) -> list[dict[str, str]]:
        """Build messages for LLM"""
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Task: {self.task}\n\nCurrent page state:\n{json.dumps(page_state, indent=2)}"},
        ]
        return messages

    async def _execute_action(self, response: str) -> ActionResult:
        """Execute action from LLM response"""
        try:
            # Parse JSON response
            action_data = json.loads(response)
            action = action_data.get("action", "")
            params = action_data.get("params", {})

            logger.info(f"Executing action: {action} with params: {params}")

            # Execute action
            result = await self._do_action(action, params)

            # Record action
            self.history.add_action({
                "action": action,
                "params": params,
                "result": result.model_dump(),
            })

            return result

        except json.JSONDecodeError:
            return ActionResult(success=False, error=f"Invalid JSON response: {response[:100]}")
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    async def _do_action(self, action: str, params: dict[str, Any]) -> ActionResult:
        """Execute specific action"""
        if action == "navigate":
            url = params.get("url", "")
            await self.browser.goto(url)
            self.history.add_url(url)
            return ActionResult(success=True, extracted_content=f"Navigated to {url}")

        elif action == "click":
            index = params.get("index", 0)
            elements = await self.browser.get_clickable_elements()
            if index < len(elements):
                selector = f"{elements[index].tag}[{index}]"
                # Build selector from element attributes
                el = elements[index]
                if el.attributes.get("id"):
                    selector = f"#{el.attributes['id']}"
                elif el.attributes.get("class"):
                    selector = f".{el.attributes['class'].split()[0]}"
                await self.browser.click(selector)
                return ActionResult(success=True, extracted_content=f"Clicked element {index}")
            return ActionResult(success=False, error=f"Element {index} not found")

        elif action == "input":
            index = params.get("index", 0)
            text = params.get("text", "")
            elements = await self.browser.get_clickable_elements()
            if index < len(elements):
                el = elements[index]
                if el.attributes.get("id"):
                    selector = f"#{el.attributes['id']}"
                elif el.attributes.get("name"):
                    selector = f"[name='{el.attributes['name']}']"
                else:
                    selector = f"{el.tag}[{index}]"
                await self.browser.type(selector, text)
                return ActionResult(success=True, extracted_content=f"Input text into element {index}")
            return ActionResult(success=False, error=f"Element {index} not found")

        elif action == "scroll":
            direction = params.get("direction", "down")
            amount = params.get("amount", 500)
            await self.browser.scroll(direction, amount)
            return ActionResult(success=True, extracted_content=f"Scrolled {direction}")

        elif action == "wait":
            seconds = params.get("seconds", 1)
            await asyncio.sleep(seconds)
            return ActionResult(success=True, extracted_content=f"Waited {seconds}s")

        elif action == "extract":
            selector = params.get("selector")
            if selector:
                html = await self.browser.get_html()
                # Simple extraction (could be enhanced with BeautifulSoup)
                return ActionResult(success=True, extracted_content=f"Extracted content")
            return ActionResult(success=False, error="No selector provided")

        elif action == "screenshot":
            screenshot = await self.browser.screenshot()
            if isinstance(screenshot, bytes):
                import base64
                screenshot = base64.b64encode(screenshot).decode()
            self.history.add_screenshot(screenshot)
            return ActionResult(success=True, extracted_content="Screenshot taken")

        elif action == "done":
            result_text = params.get("result", "Task completed")
            return ActionResult(success=True, extracted_content=result_text, is_done=True)

        elif action == "error":
            error_msg = params.get("message", "Unknown error")
            return ActionResult(success=False, error=error_msg)

        else:
            return ActionResult(success=False, error=f"Unknown action: {action}")
