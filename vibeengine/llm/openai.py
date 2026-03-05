"""OpenAI LLM provider"""

import os
from typing import Any

from openai import AsyncOpenAI

from vibeengine.llm.base import BaseLLM
from vibeengine.config import settings


class ChatOpenAI(BaseLLM):
    """OpenAI ChatGPT provider"""

    def __init__(
        self,
        model: str = "gpt-4",
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs: Any,
    ):
        self.model = model
        self.api_key = api_key or settings.openai_api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url
        self.extra_kwargs = kwargs

        if not self.api_key:
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY or pass api_key.")

        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            **kwargs,
        )

    async def chat(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            **kwargs,
        )
        return response.choices[0].message.content or ""

    async def chat_with_structured_output(
        self,
        messages: list[dict[str, str]],
        response_model: type,
        **kwargs: Any,
    ) -> Any:
        response = await self.client.beta.chat.completions.parse(
            model=self.model,
            messages=messages,
            response_format=response_model,
            **kwargs,
        )
        return response.choices[0].message.parsed

    @property
    def model_name(self) -> str:
        return self.model
