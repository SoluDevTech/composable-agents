"""Tests for tracing dependency injection (_create_tracing_provider).

Uses real NoopTracingProvider (internal).
Mocks langfuse/phoenix modules (external tracing services).
"""

import os
import pytest
from src.config import Settings, TracingSettings
from src.dependencies import _create_tracing_provider
from src.infrastructure.tracing.noop_adapter import NoopTracingProvider


class TestTracingDependencyInjection:
    def test_default_settings_create_noop_provider(self, monkeypatch):
        """When tracing is disabled, _create_tracing_provider returns NoopTracingProvider."""
        # Clear environment variables that might interfere
        monkeypatch.delenv("ENABLED", raising=False)
        monkeypatch.delenv("PROVIDER", raising=False)
        
        tracing = TracingSettings(provider="none", enabled=False)
        settings = Settings(agents_dir="./agents", tracing=tracing)
        provider = _create_tracing_provider(settings)

        assert isinstance(provider, NoopTracingProvider)

    def test_disabled_langfuse_creates_noop_provider(self, monkeypatch):
        """When langfuse is disabled, _create_tracing_provider returns NoopTracingProvider."""
    
        tracing = TracingSettings(provider="langfuse", enabled=False)
        settings = Settings(agents_dir="./agents", tracing=tracing)
        provider = _create_tracing_provider(settings)

        assert isinstance(provider, NoopTracingProvider)

    def test_disabled_phoenix_creates_noop_provider(self, monkeypatch):
        """When phoenix is disabled, _create_tracing_provider returns NoopTracingProvider."""
        
        tracing = TracingSettings(provider="phoenix", enabled=False)
        settings = Settings(agents_dir="./agents", tracing=tracing)
        provider = _create_tracing_provider(settings)

        assert isinstance(provider, NoopTracingProvider)

    def test_unknown_provider_creates_noop(self, monkeypatch):
        """When provider is unknown, _create_tracing_provider returns NoopTracingProvider."""
        
        tracing = TracingSettings(provider="unknown", enabled=True)
        settings = Settings(agents_dir="./agents", tracing=tracing)
        provider = _create_tracing_provider(settings)

        assert isinstance(provider, NoopTracingProvider)