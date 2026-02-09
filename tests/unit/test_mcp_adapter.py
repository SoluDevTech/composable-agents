from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.entities.mcp_server_config import McpServerConfig, McpTransportType
from src.domain.exceptions import McpConnectionError, McpToolLoadError
from src.infrastructure.mcp.adapter import LangchainMcpToolLoader


class TestLoadToolsStdio:
    @pytest.mark.asyncio
    async def test_load_tools_stdio(self):
        configs = [
            McpServerConfig(
                name="filesystem",
                transport=McpTransportType.STDIO,
                command="npx",
                args=["-y", "@modelcontextprotocol/server-filesystem"],
                env={"HOME": "/tmp"},
            )
        ]

        mock_tools = [MagicMock(name="read_file"), MagicMock(name="write_file")]
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=mock_tools)

        with patch(
            "src.infrastructure.mcp.adapter.MultiServerMCPClient",
            return_value=mock_client,
        ) as mock_cls:
            loader = LangchainMcpToolLoader()
            tools = await loader.load_tools(configs)

            mock_cls.assert_called_once()
            call_args = mock_cls.call_args[0][0]
            assert "filesystem" in call_args
            assert call_args["filesystem"]["transport"] == "stdio"
            assert call_args["filesystem"]["command"] == "npx"
            assert call_args["filesystem"]["args"] == [
                "-y",
                "@modelcontextprotocol/server-filesystem",
            ]
            assert call_args["filesystem"]["env"] == {"HOME": "/tmp"}
            assert tools == mock_tools


class TestLoadToolsHttp:
    @pytest.mark.asyncio
    async def test_load_tools_http(self):
        configs = [
            McpServerConfig(
                name="web-search",
                transport=McpTransportType.HTTP,
                url="http://localhost:3001/mcp",
                headers={"Authorization": "Bearer my-token"},
            )
        ]

        mock_tools = [MagicMock(name="search")]
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=mock_tools)

        with patch(
            "src.infrastructure.mcp.adapter.MultiServerMCPClient",
            return_value=mock_client,
        ) as mock_cls:
            loader = LangchainMcpToolLoader()
            tools = await loader.load_tools(configs)

            mock_cls.assert_called_once()
            call_args = mock_cls.call_args[0][0]
            assert "web-search" in call_args
            assert call_args["web-search"]["transport"] == "streamable_http"
            assert call_args["web-search"]["url"] == "http://localhost:3001/mcp"
            assert call_args["web-search"]["headers"] == {
                "Authorization": "Bearer my-token"
            }
            assert tools == mock_tools


class TestConnectionError:
    @pytest.mark.asyncio
    async def test_connection_error_raises_mcp_connection_error(self):
        configs = [
            McpServerConfig(
                name="failing",
                transport=McpTransportType.STDIO,
                command="bad-cmd",
            )
        ]

        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(
            side_effect=ConnectionError("connection refused")
        )

        with patch(
            "src.infrastructure.mcp.adapter.MultiServerMCPClient",
            return_value=mock_client,
        ):
            loader = LangchainMcpToolLoader()
            with pytest.raises(McpConnectionError, match="Failed to connect"):
                await loader.load_tools(configs)

    @pytest.mark.asyncio
    async def test_generic_error_raises_mcp_tool_load_error(self):
        configs = [
            McpServerConfig(
                name="failing",
                transport=McpTransportType.STDIO,
                command="bad-cmd",
            )
        ]

        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(
            side_effect=RuntimeError("unexpected error")
        )

        with patch(
            "src.infrastructure.mcp.adapter.MultiServerMCPClient",
            return_value=mock_client,
        ):
            loader = LangchainMcpToolLoader()
            with pytest.raises(McpToolLoadError, match="Failed to load MCP tools"):
                await loader.load_tools(configs)


class TestResolveEnvVars:
    def test_resolve_env_vars(self, monkeypatch):
        monkeypatch.setenv("MY_TOKEN", "secret-123")
        loader = LangchainMcpToolLoader()
        result = loader._resolve_env_vars({"Authorization": "Bearer ${MY_TOKEN}"})
        assert result == {"Authorization": "Bearer secret-123"}

    def test_resolve_env_vars_missing_keeps_placeholder(self, monkeypatch):
        monkeypatch.delenv("NONEXISTENT_VAR", raising=False)
        loader = LangchainMcpToolLoader()
        result = loader._resolve_env_vars({"key": "value-${NONEXISTENT_VAR}-end"})
        assert result == {"key": "value-${NONEXISTENT_VAR}-end"}

    def test_resolve_env_vars_multiple_vars(self, monkeypatch):
        monkeypatch.setenv("HOST", "localhost")
        monkeypatch.setenv("PORT", "8080")
        loader = LangchainMcpToolLoader()
        result = loader._resolve_env_vars({"url": "http://${HOST}:${PORT}/api"})
        assert result == {"url": "http://localhost:8080/api"}

    def test_resolve_env_vars_empty_dict(self):
        loader = LangchainMcpToolLoader()
        result = loader._resolve_env_vars({})
        assert result == {}

    def test_resolve_env_vars_no_placeholders(self):
        loader = LangchainMcpToolLoader()
        result = loader._resolve_env_vars({"key": "plain-value"})
        assert result == {"key": "plain-value"}


class TestClose:
    @pytest.mark.asyncio
    async def test_close_clears_clients(self):
        loader = LangchainMcpToolLoader()
        loader._clients = [MagicMock(), MagicMock()]
        assert len(loader._clients) == 2

        await loader.close()
        assert len(loader._clients) == 0
