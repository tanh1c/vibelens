"""Ollama local LLM provider"""

import os
from typing import Any

from vibeengine.llm.base import BaseLLM


class ChatOllama(BaseLLM):
    """Ollama local LLM provider"""

    def __init__(
        self,
        model: str = "llama3",
        base_url: str = "http://localhost:11434",
        **kwargs: Any,
    ):
        self.model = model
        self.base_url = base_url
        self.extra_kwargs = kwargs
        self._client: Any = None

    @property
    def client(self) -> Any:
        """Lazy import and create client"""
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=120.0)
        return self._client

    async def chat(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            **self.extra_kwargs,
            **kwargs,
        }

        response = await self.client.post("/api/chat", json=payload)
        response.raise_for_status()

        data = response.json()
        return data["message"]["content"]

    async def chat_with_structured_output(
        self,
        messages: list[dict[str, str]],
        response_model: type,
        **kwargs: Any,
    ) -> Any:
        # Ollama doesn't support structured output directly
        # Return raw text for now
        text = await self.chat(messages, **kwargs)
        return text

    @property
    def model_name(self) -> str:
        return self.model
