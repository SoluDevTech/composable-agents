"""Tests for MCP lifecycle in dependencies (module-level wiring and lifespan cleanup).

Uses mock_mcp_tool_loader (external) for the MCP adapter.
Verifies module-level singletons are wired correctly and lifespan cleanup works.
"""

from unittest.mock import AsyncMock, patch

from src import dependencies
from src.infrastructure.mcp.adapter import LangchainMcpToolLoader


class TestModuleLevelMcpWiring:
    """Tests that module-level singletons are wired correctly for MCP."""

    def test_mcp_tool_loader_is_langchain_instance(self):
        """The module-level mcp_tool_loader is a LangchainMcpToolLoader."""
        assert isinstance(dependencies.mcp_tool_loader, LangchainMcpToolLoader)


class TestLifespanMcpCleanup:
    """Tests for lifespan MCP cleanup."""

    async def test_lifespan_calls_mcp_tool_loader_close(self, mock_mcp_tool_loader):
        """Lifespan shutdown calls close() on the mcp_tool_loader."""
        from src.main import lifespan

        with (
            patch("src.main.mcp_tool_loader", mock_mcp_tool_loader),
            patch("src.main.close_persistence", AsyncMock()),
            patch("src.main.init_persistence", AsyncMock()),
            patch("src.main.tracing_provider", AsyncMock()),
        ):
            async with lifespan(None):
                pass  # enter and exit context to trigger cleanup

            assert mock_mcp_tool_loader._closed is True

    async def test_lifespan_handles_cleanup_gracefully(self):
        """Lifespan shutdown calls close/flush/shutdown on all singletons."""
        from src.main import lifespan

        mock_close_persistence = AsyncMock()
        mock_mcp = AsyncMock()
        mock_tracing = AsyncMock()

        with (
            patch("src.main.close_persistence", mock_close_persistence),
            patch("src.main.init_persistence", AsyncMock()),
            patch("src.main.mcp_tool_loader", mock_mcp),
            patch("src.main.tracing_provider", mock_tracing),
        ):
            async with lifespan(None):
                pass  # enter and exit context to trigger cleanup

            mock_close_persistence.assert_awaited_once()
            mock_mcp.close.assert_awaited_once()
            mock_tracing.flush.assert_awaited_once()
            mock_tracing.shutdown.assert_awaited_once()
