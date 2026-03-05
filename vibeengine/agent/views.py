"""Agent data models"""

from typing import Any
from pydantic import BaseModel, Field
from datetime import datetime


class ActionResult(BaseModel):
    """Result from a browser action"""
    success: bool = True
    extracted_content: str | None = None
    error: str | None = None
    is_done: bool = False
    attachments: list[str] = Field(default_factory=list)


class AgentConfig(BaseModel):
    """Agent configuration"""
    task: str
    llm_model: str = "gpt-4"
    max_steps: int = 100
    max_actions_per_step: int = 3
    max_failures: int = 3
    use_vision: bool = True
    use_thinking: bool = True
    timeout: int = 90  # seconds
    step_timeout: int = 120  # seconds


class AgentHistory(BaseModel):
    """Agent execution history"""
    urls: list[str] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    screenshots: list[str] = Field(default_factory=list)  # base64
    extracted_content: list[str] = Field(default_factory=list)
    errors: list[str | None] = Field(default_factory=list)
    timestamps: list[datetime] = Field(default_factory=list)

    def add_url(self, url: str) -> None:
        self.urls.append(url)

    def add_action(self, action: dict[str, Any]) -> None:
        self.actions.append(action)

    def add_screenshot(self, screenshot: str) -> None:
        self.screenshots.append(screenshot)

    def add_extracted(self, content: str) -> None:
        self.extracted_content.append(content)

    def add_error(self, error: str | None) -> None:
        self.errors.append(error)


class AgentStep(BaseModel):
    """Single step in agent execution"""
    step_number: int
    thought: str | None = None
    action: str
    action_params: dict[str, Any] = Field(default_factory=dict)
    result: ActionResult
    timestamp: datetime = Field(default_factory=datetime.now)
