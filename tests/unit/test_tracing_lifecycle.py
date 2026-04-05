"""Tests for tracing lifecycle (flush/shutdown via lifespan).

Uses mock_tracing_provider for verifying flush/shutdown calls (external).
"""

from unittest.mock import AsyncMock, patch


class TestTracingLifecycle:
    async def test_lifespan_calls_tracing_flush(self, mock_tracing_provider):
        """Lifespan shutdown calls flush() on the tracing_provider."""
        from src.main import lifespan

        with (
            patch("src.main.close_persistence", AsyncMock()),
            patch("src.main.init_persistence", AsyncMock()),
            patch("src.main.seed_builtin_agents", AsyncMock()),
            patch("src.main.mcp_tool_loader", AsyncMock()),
            patch("src.main.tracing_provider", mock_tracing_provider),
        ):
            async with lifespan(None):
                pass  # enter and exit context to trigger cleanup

            mock_tracing_provider.flush.assert_awaited_once()

    async def test_lifespan_calls_tracing_shutdown(self, mock_tracing_provider):
        """Lifespan shutdown calls shutdown() on the tracing_provider."""
        from src.main import lifespan

        with (
            patch("src.main.close_persistence", AsyncMock()),
            patch("src.main.init_persistence", AsyncMock()),
            patch("src.main.seed_builtin_agents", AsyncMock()),
            patch("src.main.mcp_tool_loader", AsyncMock()),
            patch("src.main.tracing_provider", mock_tracing_provider),
        ):
            async with lifespan(None):
                pass  # enter and exit context to trigger cleanup

            mock_tracing_provider.shutdown.assert_awaited_once()

    async def test_lifespan_flush_before_shutdown(self, mock_tracing_provider):
        """Lifespan calls flush() before shutdown() on the tracing_provider."""
        from src.main import lifespan

        call_order = []
        original_flush = mock_tracing_provider.flush

        async def track_flush():
            call_order.append("flush")
            return await original_flush()

        original_shutdown = mock_tracing_provider.shutdown

        async def track_shutdown():
            call_order.append("shutdown")
            return await original_shutdown()

        mock_tracing_provider.flush = AsyncMock(side_effect=track_flush)
        mock_tracing_provider.shutdown = AsyncMock(side_effect=track_shutdown)

        with (
            patch("src.main.close_persistence", AsyncMock()),
            patch("src.main.init_persistence", AsyncMock()),
            patch("src.main.seed_builtin_agents", AsyncMock()),
            patch("src.main.mcp_tool_loader", AsyncMock()),
            patch("src.main.tracing_provider", mock_tracing_provider),
        ):
            async with lifespan(None):
                pass  # enter and exit context to trigger cleanup

            assert call_order == ["flush", "shutdown"]
