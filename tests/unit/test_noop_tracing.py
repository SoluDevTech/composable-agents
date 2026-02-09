import pytest

from src.infrastructure.tracing.noop_adapter import NoopTracingProvider


class TestNoopTracingProvider:
    def test_get_callbacks_returns_empty_list(self):
        provider = NoopTracingProvider()
        assert provider.get_callbacks() == []

    @pytest.mark.asyncio
    async def test_flush_does_nothing(self):
        provider = NoopTracingProvider()
        await provider.flush()

    @pytest.mark.asyncio
    async def test_shutdown_does_nothing(self):
        provider = NoopTracingProvider()
        await provider.shutdown()
