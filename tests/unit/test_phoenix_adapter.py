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

    mock_trace = MagicMock()
    mock_tracer = MagicMock()
    mock_trace.get_tracer.return_value = mock_tracer

    with patch.dict(
        "sys.modules",
        {
            "phoenix": mock_phoenix,
            "phoenix.otel": mock_phoenix_otel,
            "openinference": mock_openinference,
            "openinference.instrumentation": mock_openinference_instr,
            "openinference.instrumentation.langchain": mock_openinference_langchain,
            "opentelemetry": MagicMock(),
            "opentelemetry.trace": mock_trace,
        },
    ):
        yield {
            "register": mock_register,
            "instrumentor": mock_instrumentor,
            "tracer": mock_tracer,
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

    def test_record_cost_accepts_parameters(self, mock_phoenix_and_openinference):
        from src.infrastructure.tracing.phoenix_adapter import PhoenixTracingProvider

        provider = PhoenixTracingProvider()

        provider.record_cost(input_tokens=100, output_tokens=50, model="gpt-4o")
        provider.record_cost(input_tokens=200, output_tokens=100, model="gpt-4o-mini")

    def test_calculate_cost_gpt4o(self, mock_phoenix_and_openinference):
        from src.infrastructure.tracing.phoenix_adapter import PhoenixTracingProvider

        provider = PhoenixTracingProvider()
        cost = provider._calculate_cost(1000, 500, "gpt-4o")

        assert cost == pytest.approx(0.0075, rel=0.01)

    def test_calculate_cost_unknown_model(self, mock_phoenix_and_openinference):
        from src.infrastructure.tracing.phoenix_adapter import PhoenixTracingProvider

        provider = PhoenixTracingProvider()
        cost = provider._calculate_cost(1000, 500, "unknown-model")

        assert cost == 0.0

    async def test_flush_does_nothing(self, mock_phoenix_and_openinference):
        from src.infrastructure.tracing.phoenix_adapter import PhoenixTracingProvider

        provider = PhoenixTracingProvider()
        await provider.flush()

    async def test_shutdown_does_nothing(self, mock_phoenix_and_openinference):
        from src.infrastructure.tracing.phoenix_adapter import PhoenixTracingProvider

        provider = PhoenixTracingProvider()
        await provider.shutdown()
