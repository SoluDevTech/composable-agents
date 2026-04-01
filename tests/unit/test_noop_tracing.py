"""Tests for NoopTracingProvider (real internal implementation)."""

from src.infrastructure.tracing.noop_adapter import NoopTracingProvider


class TestNoopTracingProvider:
    def test_get_callbacks_returns_empty_list(self):
        provider = NoopTracingProvider()
        assert provider.get_callbacks() == []

    async def test_flush_does_nothing(self):
        provider = NoopTracingProvider()
        await provider.flush()

    async def test_shutdown_does_nothing(self):
        provider = NoopTracingProvider()
        await provider.shutdown()
