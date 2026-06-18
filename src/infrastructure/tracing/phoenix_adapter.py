import logging
from typing import Any

import phoenix.otel
from openinference.instrumentation.langchain import LangChainInstrumentor
from opentelemetry import trace

from src.domain.logging.messages import LogMessage
from src.domain.ports.tracing_provider import TracingProvider

logger = logging.getLogger(__name__)


class PhoenixTracingProvider(TracingProvider):
    """Tracing provider using Arize Phoenix with OpenTelemetry auto-instrumentation."""

    def __init__(
        self,
        endpoint: str | None = None,
        api_key: str | None = None,
        project_name: str | None = None,
    ):
        endpoint = endpoint or "http://localhost:6006"
        project_name = project_name or "composable-agents"

        # Ensure endpoint has the /v1/traces path
        if endpoint and not endpoint.endswith("/v1/traces"):
            endpoint = f"{endpoint.rstrip('/')}/v1/traces"

        logger.info(
            LogMessage.PHOENIX_PROVIDER_INIT,
            endpoint,
            project_name,
        )

        # Register with explicit protocol and batching
        phoenix.otel.register(
            endpoint=endpoint,
            project_name=project_name,
            headers={"api_key": api_key} if api_key else None,
            protocol="http/protobuf",
            batch=True,
            auto_instrument=True,
        )

        LangChainInstrumentor().instrument()

        # Store tracer provider for flush/shutdown
        self._tracer_provider = trace.get_tracer_provider()
        self._instrumented = True
        logger.info(LogMessage.PHOENIX_TRACING_INITIALIZED)

    def get_callbacks(self) -> list[Any]:
        """Return an empty list since Phoenix uses OpenTelemetry auto-instrumentation."""
        return []

    async def flush(self) -> None:
        """Force flush all pending spans to Phoenix."""
        if self._tracer_provider is None:
            return

        try:
            timeout_millis = 30000
            if hasattr(self._tracer_provider, "force_flush"):
                self._tracer_provider.force_flush(timeout_millis=timeout_millis)
                logger.info(LogMessage.PHOENIX_SPANS_FLUSHED)
        except Exception:
            logger.exception(LogMessage.PHOENIX_FLUSH_FAILED)

    async def shutdown(self) -> None:
        """Shutdown the tracer provider and flush remaining spans."""
        if self._tracer_provider is None:
            return

        try:
            await self.flush()
            if hasattr(self._tracer_provider, "shutdown"):
                self._tracer_provider.shutdown()
                logger.info(LogMessage.PHOENIX_TRACING_SHUTDOWN)
        except Exception:
            logger.exception(LogMessage.TRACER_SHUTDOWN_FAILED)
