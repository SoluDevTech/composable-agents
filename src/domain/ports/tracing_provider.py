from abc import ABC, abstractmethod
from typing import Any


class TracingProvider(ABC):
    @abstractmethod
    def get_callbacks(self) -> list[Any]:
        """Return LangChain callbacks for tracing."""
        ...

    @abstractmethod
    async def flush(self) -> None:
        """Force sending pending traces."""
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """Clean shutdown of the tracing provider."""
        ...

    def record_cost(self, input_tokens: int = 0, output_tokens: int = 0, model: str = "unknown") -> None:
        """Record token usage and cost for a request."""
        pass
