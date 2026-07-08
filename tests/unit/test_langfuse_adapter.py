"""Tests for LangfuseTracingProvider.

The ``langfuse`` module is an external tracing service and is mocked via
sys.modules injection. The adapter import MUST happen inside each test (after
the fixture has injected the mock module) — this is a documented exception to
the "imports at module top" convention because the adapter imports
``langfuse.callback.CallbackHandler`` at module load time.
"""

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _mock_langfuse_module():
    """Inject a fake langfuse module into sys.modules so the adapter can import it."""
    mock_handler_class = MagicMock()

    langfuse_mod = ModuleType("langfuse")
    langfuse_callback_mod = ModuleType("langfuse.callback")
    langfuse_callback_mod.CallbackHandler = mock_handler_class
    langfuse_mod.callback = langfuse_callback_mod

    sys.modules["langfuse"] = langfuse_mod
    sys.modules["langfuse.callback"] = langfuse_callback_mod

    sys.modules.pop("src.infrastructure.tracing.langfuse_adapter", None)

    yield mock_handler_class

    sys.modules.pop("langfuse", None)
    sys.modules.pop("langfuse.callback", None)
    sys.modules.pop("src.infrastructure.tracing.langfuse_adapter", None)


class TestLangfuseTracingProvider:
    def test_get_callbacks_returns_handler(self, _mock_langfuse_module):
        # Arrange
        mock_handler_class = _mock_langfuse_module
        mock_handler = MagicMock()
        mock_handler_class.return_value = mock_handler

        # Act — import here so the adapter picks up the mocked langfuse module
        from src.infrastructure.tracing.langfuse_adapter import LangfuseTracingProvider

        provider = LangfuseTracingProvider(
            public_key="pk-test",
            secret_key="sk-test",
            host="https://langfuse.example.com",
        )
        callbacks = provider.get_callbacks()

        # Assert
        assert len(callbacks) == 1
        assert callbacks[0] is mock_handler
        mock_handler_class.assert_called_once_with(
            public_key="pk-test",
            secret_key="sk-test",
            host="https://langfuse.example.com",
        )

    async def test_flush_calls_handler_flush(self, _mock_langfuse_module):
        # Arrange
        mock_handler_class = _mock_langfuse_module
        mock_handler = MagicMock()
        mock_handler_class.return_value = mock_handler

        from src.infrastructure.tracing.langfuse_adapter import LangfuseTracingProvider

        provider = LangfuseTracingProvider(public_key="pk", secret_key="sk")

        # Act
        await provider.flush()

        # Assert
        mock_handler.flush.assert_called_once()

    async def test_shutdown_calls_handler_flush(self, _mock_langfuse_module):
        # Arrange
        mock_handler_class = _mock_langfuse_module
        mock_handler = MagicMock()
        mock_handler_class.return_value = mock_handler

        from src.infrastructure.tracing.langfuse_adapter import LangfuseTracingProvider

        provider = LangfuseTracingProvider(public_key="pk", secret_key="sk")

        # Act
        await provider.shutdown()

        # Assert
        mock_handler.flush.assert_called_once()

    def test_constructor_without_host_passes_none(self, _mock_langfuse_module):
        # Arrange
        mock_handler_class = _mock_langfuse_module
        mock_handler = MagicMock()
        mock_handler_class.return_value = mock_handler

        from src.infrastructure.tracing.langfuse_adapter import LangfuseTracingProvider

        # Act
        LangfuseTracingProvider(public_key="pk", secret_key="sk")

        # Assert
        mock_handler_class.assert_called_once_with(
            public_key="pk",
            secret_key="sk",
            host=None,
        )
