"""Tests for PhoenixTracingProvider.

Phoenix and openinference modules are mocked (external tracing service).
"""

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _mock_phoenix_modules():
    """Inject fake phoenix and openinference modules into sys.modules."""
    mock_register = MagicMock()
    mock_instrumentor_class = MagicMock()
    mock_instrumentor_instance = MagicMock()
    mock_instrumentor_class.return_value = mock_instrumentor_instance

    # Build phoenix.otel module
    phoenix_mod = ModuleType("phoenix")
    phoenix_otel_mod = ModuleType("phoenix.otel")
    phoenix_otel_mod.register = mock_register
    phoenix_mod.otel = phoenix_otel_mod

    # Build openinference.instrumentation.langchain module
    openinference_mod = ModuleType("openinference")
    openinference_instrumentation_mod = ModuleType("openinference.instrumentation")
    openinference_langchain_mod = ModuleType("openinference.instrumentation.langchain")
    openinference_langchain_mod.LangChainInstrumentor = mock_instrumentor_class
    openinference_instrumentation_mod.langchain = openinference_langchain_mod
    openinference_mod.instrumentation = openinference_instrumentation_mod

    sys.modules["phoenix"] = phoenix_mod
    sys.modules["phoenix.otel"] = phoenix_otel_mod
    sys.modules["openinference"] = openinference_mod
    sys.modules["openinference.instrumentation"] = openinference_instrumentation_mod
    sys.modules["openinference.instrumentation.langchain"] = openinference_langchain_mod

    # Clear cached import of the adapter
    sys.modules.pop("src.infrastructure.tracing.phoenix_adapter", None)

    yield mock_register, mock_instrumentor_class, mock_instrumentor_instance

    for mod_name in [
        "phoenix",
        "phoenix.otel",
        "openinference",
        "openinference.instrumentation",
        "openinference.instrumentation.langchain",
        "src.infrastructure.tracing.phoenix_adapter",
    ]:
        sys.modules.pop(mod_name, None)


class TestPhoenixTracingProvider:
    def test_constructor_calls_register_and_instrument(self, _mock_phoenix_modules):
        mock_register, _, mock_instrumentor_instance = _mock_phoenix_modules

        from src.infrastructure.tracing.phoenix_adapter import PhoenixTracingProvider

        PhoenixTracingProvider(
            endpoint="http://phoenix:6006",
            api_key="my-api-key",
            project_name="my-project",
        )

        mock_register.assert_called_once_with(
            endpoint="http://phoenix:6006",
            project_name="my-project",
            headers={"api_key": "my-api-key"},
        )
        mock_instrumentor_instance.instrument.assert_called_once()

    def test_constructor_defaults(self, _mock_phoenix_modules):
        mock_register, _, _ = _mock_phoenix_modules

        from src.infrastructure.tracing.phoenix_adapter import PhoenixTracingProvider

        PhoenixTracingProvider()

        mock_register.assert_called_once_with(
            endpoint="http://localhost:6006",
            project_name="composable-agents",
            headers=None,
        )

    def test_get_callbacks_returns_empty_list(self, _mock_phoenix_modules):
        from src.infrastructure.tracing.phoenix_adapter import PhoenixTracingProvider

        provider = PhoenixTracingProvider()

        assert provider.get_callbacks() == []

    async def test_flush_does_nothing(self, _mock_phoenix_modules):
        from src.infrastructure.tracing.phoenix_adapter import PhoenixTracingProvider

        provider = PhoenixTracingProvider()
        await provider.flush()

    async def test_shutdown_does_nothing(self, _mock_phoenix_modules):
        from src.infrastructure.tracing.phoenix_adapter import PhoenixTracingProvider

        provider = PhoenixTracingProvider()
        await provider.shutdown()
