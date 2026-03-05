"""Base LLM interface"""

from abc import ABC, abstractmethod
from typing import Any, Literal


class BaseLLM(ABC):
    """Base class for LLM providers"""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> str:
        """Send a chat request and return the response"""
        pass

    @abstractmethod
    async def chat_with_structured_output(
        self,
        messages: list[dict[str, str]],
        response_model: type,
        **kwargs: Any,
    ) -> Any:
        """Send a chat request with structured output"""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Get the model name"""
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model={self.model_name})"
