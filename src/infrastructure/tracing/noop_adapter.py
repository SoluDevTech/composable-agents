from typing import Any

from src.domain.ports.tracing_provider import TracingProvider


class NoopTracingProvider(TracingProvider):
    """Tracing provider that does nothing.

    Used when tracing is disabled or no provider is configured.
    """

    def get_callbacks(self) -> list[Any]:
        """Return an empty list of callbacks."""
        return []

    async def flush(self) -> None:
        """No-op flush."""
        pass

    async def shutdown(self) -> None:
        """No-op shutdown."""
        pass
