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
    def test_default_settings_create_noop_provider(self, monkeypatch):
        monkeypatch.setenv("TRACING_ENABLED", "false")
        from src.config import Settings
        from importlib import reload
        import src.config

        reload(src.config)

        settings = Settings(agents_dir="./agents")
        provider = _create_tracing_provider(settings)

        assert isinstance(provider, NoopTracingProvider)

    def test_disabled_langfuse_creates_noop_provider(self):
        tracing = TracingSettings(provider="langfuse", enabled=False)
        settings = Settings(agents_dir="./agents", tracing=tracing)
        provider = _create_tracing_provider(settings)

        assert isinstance(provider, NoopTracingProvider)

    def test_disabled_phoenix_creates_noop_provider(self):
        tracing = TracingSettings(provider="phoenix", enabled=False)
        settings = Settings(agents_dir="./agents", tracing=tracing)
        provider = _create_tracing_provider(settings)

        assert isinstance(provider, NoopTracingProvider)

    def test_unknown_provider_creates_noop(self):
        tracing = TracingSettings(provider="unknown", enabled=True)
        settings = Settings(agents_dir="./agents", tracing=tracing)
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
            settings = Settings(agents_dir="./agents", tracing=tracing)
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
        import sys
        from types import ModuleType
        from unittest.mock import MagicMock, patch

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

        with patch.dict(
            "sys.modules",
            {
                "phoenix": mock_phoenix,
                "phoenix.otel": mock_phoenix_otel,
                "openinference": mock_openinference,
                "openinference.instrumentation": mock_openinference_instr,
                "openinference.instrumentation.langchain": mock_openinference_langchain,
            },
        ):
            from src.infrastructure.tracing.phoenix_adapter import PhoenixTracingProvider

            tracing = TracingSettings(
                provider="phoenix",
                enabled=True,
                phoenix_collector_endpoint="http://phoenix:6006",
                phoenix_api_key="my-key",
                project_name="my-project",
            )
            settings = Settings(agents_dir="./agents", tracing=tracing)
            provider = _create_tracing_provider(settings)

            assert isinstance(provider, PhoenixTracingProvider)
