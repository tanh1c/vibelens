"""Anthropic LLM provider (Claude)"""

import os
from typing import Any

from anthropic import AsyncAnthropic

from vibeengine.llm.base import BaseLLM
from vibeengine.config import settings


class ChatAnthropic(BaseLLM):
    """Anthropic Claude provider"""

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: str | None = None,
        **kwargs: Any,
    ):
        self.model = model
        self.api_key = api_key or settings.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
        self.extra_kwargs = kwargs

        if not self.api_key:
            raise ValueError(
                "Anthropic API key is required. Set ANTHROPIC_API_KEY or pass api_key."
            )

        self.client = AsyncAnthropic(
            api_key=self.api_key,
            **kwargs,
        )

    async def chat(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> str:
        # Convert messages to Anthropic format
        system = ""
        anthropic_messages = []

        for msg in messages:
            if msg.get("role") == "system":
                system = msg.get("content", "")
            else:
                role = "assistant" if msg.get("role") == "assistant" else "user"
                anthropic_messages.append({
                    "role": role,
                    "content": msg.get("content", "")
                })

        response = await self.client.messages.create(
            model=self.model,
            system=system,
            messages=anthropic_messages,
            **kwargs,
        )
        return response.content[0].text

    async def chat_with_structured_output(
        self,
        messages: list[dict[str, str]],
        response_model: type,
        **kwargs: Any,
    ) -> Any:
        # Anthropic doesn't support structured output directly yet
        # Use text output and parse
        text = await self.chat(messages, **kwargs)
        # For now, return raw text - can be enhanced with JSON parsing
        return text

    @property
    def model_name(self) -> str:
        return self.model
