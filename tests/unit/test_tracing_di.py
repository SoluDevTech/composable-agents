"""Tests for tracing dependency injection (_create_tracing_provider).

Uses real NoopTracingProvider (internal). Verifies that disabled/unknown
tracing configurations yield a NoopTracingProvider.
"""

from src.config import Settings, TracingSettings
from src.dependencies import _create_tracing_provider
from src.infrastructure.tracing.noop_adapter import NoopTracingProvider


class TestTracingDependencyInjection:
    def test_default_settings_create_noop_provider(self):
        # Arrange
        tracing = TracingSettings(provider="none", enabled=False)
        settings = Settings(tracing=tracing)

        # Act
        provider = _create_tracing_provider(settings)

        # Assert
        assert isinstance(provider, NoopTracingProvider)

    def test_disabled_langfuse_creates_noop_provider(self):
        # Arrange
        tracing = TracingSettings(provider="langfuse", enabled=False)
        settings = Settings(tracing=tracing)

        # Act
        provider = _create_tracing_provider(settings)

        # Assert
        assert isinstance(provider, NoopTracingProvider)

    def test_disabled_phoenix_creates_noop_provider(self):
        # Arrange
        tracing = TracingSettings(provider="phoenix", enabled=False)
        settings = Settings(tracing=tracing)

        # Act
        provider = _create_tracing_provider(settings)

        # Assert
        assert isinstance(provider, NoopTracingProvider)

    def test_unknown_provider_creates_noop(self):
        # Arrange
        tracing = TracingSettings(provider="unknown", enabled=True)
        settings = Settings(tracing=tracing)

        # Act
        provider = _create_tracing_provider(settings)

        # Assert
        assert isinstance(provider, NoopTracingProvider)
