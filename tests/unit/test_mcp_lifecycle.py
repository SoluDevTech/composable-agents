"""Tests for MCP lifecycle in dependencies and main.py lifespan.

Uses ``mock_mcp_tool_loader`` from external.py (external MCP boundary).
Verifies module-level wiring and lifespan cleanup via observable behavior.
"""

from unittest.mock import AsyncMock, patch

from src import dependencies
from src.infrastructure.mcp.adapter import LangchainMcpToolLoader
from src.main import lifespan


class TestModuleLevelMcpWiring:
    def test_mcp_tool_loader_is_langchain_instance(self):
        # Arrange
        # Act
        loader = dependencies.mcp_tool_loader

        # Assert
        assert isinstance(loader, LangchainMcpToolLoader)


class TestLifespanMcpCleanup:
    async def test_lifespan_calls_mcp_tool_loader_close(self, mock_mcp_tool_loader):
        # Arrange
        mock_tracing = AsyncMock()

        # Act
        with (
            patch("src.main.mcp_tool_loader", mock_mcp_tool_loader),
            patch("src.main.close_persistence", AsyncMock()),
            patch("src.main.init_persistence", AsyncMock()),
            patch("src.main.tracing_provider", mock_tracing),
        ):
            async with lifespan(None):
                pass

        # Assert
        mock_mcp_tool_loader.close.assert_awaited_once()

    async def test_lifespan_handles_cleanup_gracefully(self):
        # Arrange
        mock_close_persistence = AsyncMock()
        mock_mcp = AsyncMock()
        mock_tracing = AsyncMock()

        # Act
        with (
            patch("src.main.close_persistence", mock_close_persistence),
            patch("src.main.init_persistence", AsyncMock()),
            patch("src.main.mcp_tool_loader", mock_mcp),
            patch("src.main.tracing_provider", mock_tracing),
        ):
            async with lifespan(None):
                pass

        # Assert
        mock_close_persistence.assert_awaited_once()
        mock_mcp.close.assert_awaited_once()
        mock_tracing.flush.assert_awaited_once()
        mock_tracing.shutdown.assert_awaited_once()
