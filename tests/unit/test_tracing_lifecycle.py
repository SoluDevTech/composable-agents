"""Tests for tracing lifecycle (flush/shutdown via lifespan).

Uses ``mock_tracing_provider`` from external.py (external tracing boundary).
"""

from unittest.mock import AsyncMock, patch

from src.main import lifespan


class TestTracingLifecycle:
    async def test_lifespan_calls_tracing_flush(self, mock_tracing_provider):
        # Arrange
        with (
            patch("src.main.close_persistence", AsyncMock()),
            patch("src.main.init_persistence", AsyncMock()),
            patch("src.main.mcp_tool_loader", AsyncMock()),
            patch("src.main.tracing_provider", mock_tracing_provider),
        ):
            # Act
            async with lifespan(None):
                pass

        # Assert
        mock_tracing_provider.flush.assert_awaited_once()

    async def test_lifespan_calls_tracing_shutdown(self, mock_tracing_provider):
        # Arrange
        with (
            patch("src.main.close_persistence", AsyncMock()),
            patch("src.main.init_persistence", AsyncMock()),
            patch("src.main.mcp_tool_loader", AsyncMock()),
            patch("src.main.tracing_provider", mock_tracing_provider),
        ):
            # Act
            async with lifespan(None):
                pass

        # Assert
        mock_tracing_provider.shutdown.assert_awaited_once()

    async def test_lifespan_flush_before_shutdown(self, mock_tracing_provider):
        # Arrange
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
            patch("src.main.mcp_tool_loader", AsyncMock()),
            patch("src.main.tracing_provider", mock_tracing_provider),
        ):
            # Act
            async with lifespan(None):
                pass

        # Assert
        assert call_order == ["flush", "shutdown"]
