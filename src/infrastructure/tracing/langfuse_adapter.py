from typing import Any

from langfuse.callback import CallbackHandler

from src.domain.ports.tracing_provider import TracingProvider


class LangfuseTracingProvider(TracingProvider):
    """Tracing provider using Langfuse for LangChain callback-based tracing.

    Args:
        public_key: Langfuse public API key.
        secret_key: Langfuse secret API key.
        host: Optional Langfuse host URL.
    """

    def __init__(self, public_key: str, secret_key: str, host: str | None = None):
        self._handler = CallbackHandler(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
        )

    def get_callbacks(self) -> list[Any]:
        """Return the Langfuse callback handler."""
        return [self._handler]

    async def flush(self) -> None:
        """Flush pending traces to Langfuse."""
        self._handler.flush()

    async def shutdown(self) -> None:
        """Flush and shut down the Langfuse handler."""
        self._handler.flush()
