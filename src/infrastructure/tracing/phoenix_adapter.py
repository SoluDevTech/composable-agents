from typing import Any

from src.domain.ports.tracing_provider import TracingProvider


class PhoenixTracingProvider(TracingProvider):
    """Tracing provider using Arize Phoenix with OpenTelemetry auto-instrumentation.

    Phoenix uses OpenTelemetry to instrument LangChain automatically,
    so no explicit LangChain callbacks are needed.

    Args:
        endpoint: Phoenix collector endpoint URL.
        api_key: Optional Phoenix API key.
        project_name: Optional project name for trace grouping.
    """

    def __init__(
        self,
        endpoint: str | None = None,
        api_key: str | None = None,
        project_name: str | None = None,
    ):
        import phoenix.otel
        from openinference.instrumentation.langchain import LangChainInstrumentor

        phoenix.otel.register(
            endpoint=endpoint or "http://localhost:6006",
            project_name=project_name or "composable-agents",
            headers={"api_key": api_key} if api_key else None,
        )
        LangChainInstrumentor().instrument()
        self._instrumented = True

    def get_callbacks(self) -> list[Any]:
        """Return an empty list since Phoenix uses OpenTelemetry auto-instrumentation."""
        return []

    async def flush(self) -> None:
        """No-op flush. Phoenix handles flushing via OpenTelemetry."""
        pass

    async def shutdown(self) -> None:
        """No-op shutdown. Phoenix handles cleanup via OpenTelemetry."""
        pass
