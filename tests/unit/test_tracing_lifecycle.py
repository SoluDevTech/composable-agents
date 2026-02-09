import pytest

from src.dependencies import flush_tracing, shutdown_tracing, override_dependencies
from tests.doubles.fake_tracing_provider import FakeTracingProvider


class TestTracingLifecycle:
    @pytest.mark.asyncio
    async def test_flush_tracing_calls_provider_flush(self):
        provider = FakeTracingProvider()
        override_dependencies(tracing_provider=provider)

        await flush_tracing()

        assert provider.flush_called is True

    @pytest.mark.asyncio
    async def test_shutdown_tracing_calls_provider_shutdown(self):
        provider = FakeTracingProvider()
        override_dependencies(tracing_provider=provider)

        await shutdown_tracing()

        assert provider.shutdown_called is True

    @pytest.mark.asyncio
    async def test_flush_tracing_safe_when_not_initialized(self):
        """flush_tracing should not raise when _tracing_provider is None."""
        import src.dependencies as deps
        original = deps._tracing_provider
        deps._tracing_provider = None

        await flush_tracing()

        deps._tracing_provider = original

    @pytest.mark.asyncio
    async def test_shutdown_tracing_safe_when_not_initialized(self):
        """shutdown_tracing should not raise when _tracing_provider is None."""
        import src.dependencies as deps
        original = deps._tracing_provider
        deps._tracing_provider = None

        await shutdown_tracing()

        deps._tracing_provider = original
