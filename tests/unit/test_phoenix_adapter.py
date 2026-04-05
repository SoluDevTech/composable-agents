"""Tests for PhoenixTracingProvider."""

import pytest
from unittest.mock import MagicMock, patch
import sys
from types import ModuleType


@pytest.fixture(autouse=True)
def mock_phoenix_and_openinference():
    """Mock phoenix.otel and openinference modules."""
    mock_register = MagicMock()

    mock_phoenix = ModuleType("phoenix")
    mock_phoenix_otel = ModuleType("phoenix.otel")
    mock_phoenix_otel.register = mock_register
    mock_phoenix.otel = mock_phoenix_otel

    mock_instrumentor = MagicMock()

    mock_openinference = ModuleType("openinference")
    mock_openinference_instr = ModuleType("openinference.instrumentation")
    mock_openinference_langchain = ModuleType("openinference.instrumentation.langchain")
    mock_openinference_langchain.LangChainInstrumentor = MagicMock(return_value=mock_instrumentor)
    mock_openinference_instr.langchain = mock_openinference_langchain
    mock_openinference.instrumentation = mock_openinference_instr

    # Create proper mocks for opentelemetry
    mock_tracer_provider = MagicMock()
    mock_tracer_provider.force_flush = MagicMock()
    mock_tracer_provider.shutdown = MagicMock()
    
    mock_trace = MagicMock()
    mock_trace.get_tracer_provider = MagicMock(return_value=mock_tracer_provider)
    
    mock_opentelemetry = MagicMock()
    mock_opentelemetry.trace = mock_trace

    # Remove from sys.modules to force re-import with mocks
    sys.modules.pop("src.infrastructure.tracing.phoenix_adapter", None)

    with patch.dict(
        "sys.modules",
        {
            "phoenix": mock_phoenix,
            "phoenix.otel": mock_phoenix_otel,
            "openinference": mock_openinference,
            "openinference.instrumentation": mock_openinference_instr,
            "openinference.instrumentation.langchain": mock_openinference_langchain,
            "opentelemetry": mock_opentelemetry,
            "opentelemetry.trace": mock_trace,
        },
    ):
        yield {
            "register": mock_register,
            "instrumentor": mock_instrumentor,
            "tracer_provider": mock_tracer_provider,
        }


class TestPhoenixTracingProvider:
    def test_constructor_calls_register(self, mock_phoenix_and_openinference):
        mock_reg = mock_phoenix_and_openinference["register"]

        from src.infrastructure.tracing.phoenix_adapter import PhoenixTracingProvider

        provider = PhoenixTracingProvider(
            endpoint="http://phoenix:6006",
            api_key="my-api-key",
            project_name="my-project",
        )

        mock_reg.assert_called_once()
        call_kwargs = mock_reg.call_args.kwargs
        assert call_kwargs["project_name"] == "my-project"
        assert call_kwargs["headers"] == {"api_key": "my-api-key"}
        assert call_kwargs["auto_instrument"] is True
        assert call_kwargs["protocol"] == "http/protobuf"
        assert call_kwargs["batch"] is True

    def test_constructor_defaults(self, mock_phoenix_and_openinference):
        mock_reg = mock_phoenix_and_openinference["register"]

        from src.infrastructure.tracing.phoenix_adapter import PhoenixTracingProvider

        provider = PhoenixTracingProvider()

        mock_reg.assert_called_once()
        call_kwargs = mock_reg.call_args.kwargs
        assert call_kwargs["project_name"] == "composable-agents"
        assert call_kwargs["headers"] is None

    def test_get_callbacks_returns_empty_list(self, mock_phoenix_and_openinference):
        from src.infrastructure.tracing.phoenix_adapter import PhoenixTracingProvider

        provider = PhoenixTracingProvider()
        assert provider.get_callbacks() == []

    async def test_flush(self, mock_phoenix_and_openinference):
        from src.infrastructure.tracing.phoenix_adapter import PhoenixTracingProvider

        provider = PhoenixTracingProvider()
        await provider.flush()
        
        # Verify force_flush was called on the tracer provider
        provider._tracer_provider.force_flush.assert_called_once()

    async def test_shutdown(self, mock_phoenix_and_openinference):
        from src.infrastructure.tracing.phoenix_adapter import PhoenixTracingProvider

        provider = PhoenixTracingProvider()
        await provider.shutdown()
        
        # Verify shutdown was called on the tracer provider
        provider._tracer_provider.shutdown.assert_called_once()