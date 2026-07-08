"""Tests for LangchainMcpToolLoader.

MultiServerMCPClient is patched (external MCP server boundary).
Tests exercise the public ``load_tools`` and ``close`` methods only.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.tools import StructuredTool, ToolException

from src.domain.entities.mcp_server_config import McpServerConfig, McpTransportType
from src.domain.errors.mcp import McpConnectionError, McpToolLoadError
from src.infrastructure.mcp.adapter import LangchainMcpToolLoader

STDIO_CONFIG = McpServerConfig(
    name="filesystem",
    transport=McpTransportType.STDIO,
    command="npx",
    args=["-y", "@modelcontextprotocol/server-filesystem"],
    env={"HOME": "/tmp"},
)
HTTP_CONFIG = McpServerConfig(
    name="web-search",
    transport=McpTransportType.HTTP,
    url="http://localhost:3001/mcp",
    headers={"Authorization": "Bearer my-token"},
)


class TestLoadToolsStdio:
    async def test_load_tools_stdio_returns_tools(self):
        # Arrange
        mock_tools = [MagicMock(name="read_file"), MagicMock(name="write_file")]
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=mock_tools)

        # Act
        with patch(
            "src.infrastructure.mcp.adapter.MultiServerMCPClient",
            return_value=mock_client,
        ):
            loader = LangchainMcpToolLoader()
            tools = await loader.load_tools([STDIO_CONFIG])

        # Assert
        assert tools == mock_tools

    async def test_load_tools_stdio_passes_command_and_env(self):
        # Arrange
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=[])

        # Act
        with patch(
            "src.infrastructure.mcp.adapter.MultiServerMCPClient",
            return_value=mock_client,
        ) as mock_cls:
            loader = LangchainMcpToolLoader()
            await loader.load_tools([STDIO_CONFIG])

        # Assert
        call_args = mock_cls.call_args[0][0]
        assert call_args["filesystem"]["transport"] == "stdio"
        assert call_args["filesystem"]["command"] == "npx"
        assert call_args["filesystem"]["env"] == {"HOME": "/tmp"}


class TestLoadToolsHttp:
    async def test_load_tools_http_returns_tools(self):
        # Arrange
        mock_tools = [MagicMock(name="search")]
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=mock_tools)

        # Act
        with patch(
            "src.infrastructure.mcp.adapter.MultiServerMCPClient",
            return_value=mock_client,
        ):
            loader = LangchainMcpToolLoader()
            tools = await loader.load_tools([HTTP_CONFIG])

        # Assert
        assert tools == mock_tools

    async def test_load_tools_http_passes_url_and_headers(self):
        # Arrange
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=[])

        # Act
        with patch(
            "src.infrastructure.mcp.adapter.MultiServerMCPClient",
            return_value=mock_client,
        ) as mock_cls:
            loader = LangchainMcpToolLoader()
            await loader.load_tools([HTTP_CONFIG])

        # Assert
        call_args = mock_cls.call_args[0][0]
        assert call_args["web-search"]["transport"] == "streamable_http"
        assert call_args["web-search"]["url"] == "http://localhost:3001/mcp"
        assert call_args["web-search"]["headers"] == {"Authorization": "Bearer my-token"}

    async def test_load_tools_http_with_auth_token(self):
        # Arrange
        config = McpServerConfig(
            name="auth-server",
            transport=McpTransportType.HTTP,
            url="http://localhost:3001/mcp",
            auth_token="secret-token",
        )
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=[])

        # Act
        with patch(
            "src.infrastructure.mcp.adapter.MultiServerMCPClient",
            return_value=mock_client,
        ) as mock_cls:
            loader = LangchainMcpToolLoader()
            await loader.load_tools([config])

        # Assert
        call_args = mock_cls.call_args[0][0]
        assert call_args["auth-server"]["auth_token"] == "secret-token"


class TestLoadToolsEnvVarResolution:
    async def test_env_vars_resolved_in_stdio_config(self, monkeypatch):
        # Arrange
        monkeypatch.setenv("MY_TOKEN", "secret-123")
        config = McpServerConfig(
            name="filesystem",
            transport=McpTransportType.STDIO,
            command="npx",
            env={"AUTH": "Bearer ${MY_TOKEN}"},
        )
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=[])

        # Act
        with patch(
            "src.infrastructure.mcp.adapter.MultiServerMCPClient",
            return_value=mock_client,
        ) as mock_cls:
            loader = LangchainMcpToolLoader()
            await loader.load_tools([config])

        # Assert
        call_args = mock_cls.call_args[0][0]
        assert call_args["filesystem"]["env"] == {"AUTH": "Bearer secret-123"}

    async def test_env_vars_resolved_in_http_headers(self, monkeypatch):
        # Arrange
        monkeypatch.setenv("API_TOKEN", "tok-abc")
        config = McpServerConfig(
            name="web",
            transport=McpTransportType.HTTP,
            url="http://localhost:3001/mcp",
            headers={"Authorization": "Bearer ${API_TOKEN}"},
        )
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=[])

        # Act
        with patch(
            "src.infrastructure.mcp.adapter.MultiServerMCPClient",
            return_value=mock_client,
        ) as mock_cls:
            loader = LangchainMcpToolLoader()
            await loader.load_tools([config])

        # Assert
        call_args = mock_cls.call_args[0][0]
        assert call_args["web"]["headers"] == {"Authorization": "Bearer tok-abc"}

    async def test_missing_env_var_keeps_placeholder(self, monkeypatch):
        # Arrange
        monkeypatch.delenv("NONEXISTENT_VAR", raising=False)
        config = McpServerConfig(
            name="fs",
            transport=McpTransportType.STDIO,
            command="npx",
            env={"KEY": "value-${NONEXISTENT_VAR}-end"},
        )
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=[])

        # Act
        with patch(
            "src.infrastructure.mcp.adapter.MultiServerMCPClient",
            return_value=mock_client,
        ) as mock_cls:
            loader = LangchainMcpToolLoader()
            await loader.load_tools([config])

        # Assert
        call_args = mock_cls.call_args[0][0]
        assert call_args["fs"]["env"] == {"KEY": "value-${NONEXISTENT_VAR}-end"}


class TestLoadToolsErrors:
    async def test_connection_error_raises_mcp_connection_error(self):
        # Arrange
        config = McpServerConfig(name="failing", transport=McpTransportType.STDIO, command="bad-cmd")
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(side_effect=ConnectionError("connection refused"))

        # Act & Assert
        with patch("src.infrastructure.mcp.adapter.MultiServerMCPClient", return_value=mock_client):
            loader = LangchainMcpToolLoader()
            with pytest.raises(McpConnectionError, match="Failed to connect"):
                await loader.load_tools([config])

    async def test_generic_error_raises_mcp_tool_load_error(self):
        # Arrange
        config = McpServerConfig(name="failing", transport=McpTransportType.STDIO, command="bad-cmd")
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(side_effect=RuntimeError("unexpected error"))

        # Act & Assert
        with patch("src.infrastructure.mcp.adapter.MultiServerMCPClient", return_value=mock_client):
            loader = LangchainMcpToolLoader()
            with pytest.raises(McpToolLoadError, match="Failed to load MCP tools"):
                await loader.load_tools([config])


class TestClose:
    async def test_close_does_not_raise_with_no_clients(self):
        # Arrange
        loader = LangchainMcpToolLoader()

        # Act
        await loader.close()

        # Assert — close completes without raising


class TestToolTimeoutViaLoadTools:
    """Verify the per-call timeout patch is applied through load_tools."""

    async def test_hung_tool_raises_tool_exception(self):
        # Arrange
        async def _hang(**_kwargs):
            await asyncio.sleep(10)
            return "never"

        async_tool = StructuredTool(
            name="hung_tool",
            description="a tool that hangs",
            args_schema=None,
            coroutine=_hang,
        )
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=[async_tool])
        loader = LangchainMcpToolLoader(tool_timeout=0.1)

        # Act
        with patch("src.infrastructure.mcp.adapter.MultiServerMCPClient", return_value=mock_client):
            tools = await loader.load_tools([STDIO_CONFIG])

        # Assert
        assert len(tools) == 1
        with pytest.raises(ToolException, match="timed out"):
            await tools[0].coroutine()

    async def test_fast_tool_succeeds(self):
        # Arrange
        async def _fast(**_kwargs):
            return "ok"

        async_tool = StructuredTool(
            name="fast_tool",
            description="a fast tool",
            args_schema=None,
            coroutine=_fast,
        )
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=[async_tool])
        loader = LangchainMcpToolLoader(tool_timeout=5.0)

        # Act
        with patch("src.infrastructure.mcp.adapter.MultiServerMCPClient", return_value=mock_client):
            tools = await loader.load_tools([STDIO_CONFIG])

        # Assert
        result = await tools[0].coroutine()
        assert result == "ok"
