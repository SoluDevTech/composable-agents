"""Tests for TracingConfig domain entity."""

import pytest
from pydantic import ValidationError

from src.domain.entities.tracing_config import TracingConfig, TracingProviderType


class TestTracingConfig:
    def test_default_tracing_disabled(self):
        config = TracingConfig()
        assert config.provider == TracingProviderType.NONE
        assert config.enabled is False

    def test_langfuse_config(self):
        config = TracingConfig(
            provider=TracingProviderType.LANGFUSE,
            enabled=True,
            endpoint="https://my-langfuse.com",
            project_name="my-project",
        )
        assert config.provider == TracingProviderType.LANGFUSE
        assert config.enabled is True

    def test_frozen(self):
        config = TracingConfig()
        with pytest.raises(ValidationError):
            config.enabled = True
