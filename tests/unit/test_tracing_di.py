"""Tests for tracing dependency injection (_create_tracing_provider).

Uses real NoopTracingProvider (internal).
Mocks langfuse/phoenix modules (external tracing services).
"""

import sys
from types import ModuleType
from unittest.mock import MagicMock

from src.config import Settings, TracingSettings
from src.dependencies import _create_tracing_provider
from src.infrastructure.tracing.noop_adapter import NoopTracingProvider


class TestTracingDependencyInjection:
    def test_default_settings_create_noop_provider(self):
        settings = Settings()
        provider = _create_tracing_provider(settings)

        assert isinstance(provider, NoopTracingProvider)

    def test_disabled_langfuse_creates_noop_provider(self):
        tracing = TracingSettings(provider="langfuse", enabled=False)
        settings = Settings(tracing=tracing)
        provider = _create_tracing_provider(settings)

        assert isinstance(provider, NoopTracingProvider)

    def test_disabled_phoenix_creates_noop_provider(self):
        tracing = TracingSettings(provider="phoenix", enabled=False)
        settings = Settings(tracing=tracing)
        provider = _create_tracing_provider(settings)

        assert isinstance(provider, NoopTracingProvider)

    def test_unknown_provider_creates_noop(self):
        tracing = TracingSettings(provider="unknown", enabled=True)
        settings = Settings(tracing=tracing)
        provider = _create_tracing_provider(settings)

        assert isinstance(provider, NoopTracingProvider)

    def test_enabled_langfuse_creates_langfuse_provider(self):
        """When langfuse is enabled, _create_tracing_provider returns a LangfuseTracingProvider."""
        mock_handler_class = MagicMock()
        mock_handler_class.return_value = MagicMock()

        langfuse_mod = ModuleType("langfuse")
        langfuse_callback_mod = ModuleType("langfuse.callback")
        langfuse_callback_mod.CallbackHandler = mock_handler_class
        langfuse_mod.callback = langfuse_callback_mod

        sys.modules["langfuse"] = langfuse_mod
        sys.modules["langfuse.callback"] = langfuse_callback_mod
        sys.modules.pop("src.infrastructure.tracing.langfuse_adapter", None)

        try:
            from src.infrastructure.tracing.langfuse_adapter import LangfuseTracingProvider

            tracing = TracingSettings(
                provider="langfuse",
                enabled=True,
                langfuse_public_key="pk-test",
                langfuse_secret_key="sk-test",
                langfuse_host="https://langfuse.example.com",
            )
            settings = Settings(tracing=tracing)
            provider = _create_tracing_provider(settings)

            assert isinstance(provider, LangfuseTracingProvider)
            mock_handler_class.assert_called_once_with(
                public_key="pk-test",
                secret_key="sk-test",
                host="https://langfuse.example.com",
            )
        finally:
            sys.modules.pop("langfuse", None)
            sys.modules.pop("langfuse.callback", None)
            sys.modules.pop("src.infrastructure.tracing.langfuse_adapter", None)

    def test_enabled_phoenix_creates_phoenix_provider(self):
        """When phoenix is enabled, _create_tracing_provider returns a PhoenixTracingProvider."""
        mock_register = MagicMock()
        mock_instrumentor_class = MagicMock()
        mock_instrumentor_class.return_value = MagicMock()

        phoenix_mod = ModuleType("phoenix")
        phoenix_otel_mod = ModuleType("phoenix.otel")
        phoenix_otel_mod.register = mock_register
        phoenix_mod.otel = phoenix_otel_mod

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
        sys.modules.pop("src.infrastructure.tracing.phoenix_adapter", None)

        try:
            from src.infrastructure.tracing.phoenix_adapter import PhoenixTracingProvider

            tracing = TracingSettings(
                provider="phoenix",
                enabled=True,
                phoenix_collector_endpoint="http://phoenix:6006",
                phoenix_api_key="my-key",
                project_name="my-project",
            )
            settings = Settings(tracing=tracing)
            provider = _create_tracing_provider(settings)

            assert isinstance(provider, PhoenixTracingProvider)
        finally:
            for mod_name in [
                "phoenix",
                "phoenix.otel",
                "openinference",
                "openinference.instrumentation",
                "openinference.instrumentation.langchain",
                "src.infrastructure.tracing.phoenix_adapter",
            ]:
                sys.modules.pop(mod_name, None)
