from typing import Any
from src.domain.ports.tracing_provider import TracingProvider


class FakeTracingProvider(TracingProvider):
    def __init__(self, callbacks: list[Any] | None = None):
        self._callbacks = callbacks or []
        self.flush_called = False
        self.shutdown_called = False

    def get_callbacks(self) -> list[Any]:
        return self._callbacks

    async def flush(self) -> None:
        self.flush_called = True

    async def shutdown(self) -> None:
        self.shutdown_called = True
