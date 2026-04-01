"""Tests for MCP tool integration in create_agent_from_config.

Uses AsyncMock for McpToolLoader (external MCP server boundary).
Patches create_deep_agent (external LLM factory).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.entities.agent_config import AgentConfig, SubAgentConfig
from src.domain.entities.mcp_server_config import McpServerConfig, McpTransportType
from src.domain.ports.mcp_tool_loader import McpToolLoader
from src.infrastructure.deepagent.factory import create_agent_from_config


class TestFactoryMcpIntegration:
    """Tests for MCP tool integration in create_agent_from_config."""

    @pytest.fixture
    def mcp_loader_with_tool(self):
        """AsyncMock MCP loader that returns a single fake tool."""
        mock = AsyncMock(spec=McpToolLoader)
        fake_tool = MagicMock(name="mcp_read_file")
        mock.load_tools.return_value = [fake_tool]
        mock._fake_tool = fake_tool  # expose for assertions
        return mock

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_loads_mcp_tools_when_configs_present(self, mock_create, mcp_loader_with_tool):
        """MCP tools are loaded and passed to create_deep_agent when mcp_servers is set."""
        mock_create.return_value = MagicMock()

        config = AgentConfig(
            name="mcp-test",
            mcp_servers=[
                McpServerConfig(
                    name="filesystem",
                    transport=McpTransportType.STDIO,
                    command="npx",
                    args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                )
            ],
        )

        await create_agent_from_config(config, mcp_tool_loader=mcp_loader_with_tool)

        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        assert kwargs["tools"] == [mcp_loader_with_tool._fake_tool]

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_merges_local_and_mcp_tools(self, mock_create, mcp_loader_with_tool):
        """Both local tools and MCP tools are merged into a single list."""
        mock_create.return_value = MagicMock()
        fake_mcp_tool = MagicMock(name="mcp_search")
        mcp_loader_with_tool.load_tools.return_value = [fake_mcp_tool]

        config = AgentConfig(
            name="merged-tools-test",
            tools=["src.infrastructure.deepagent.example_tools:get_user_name"],
            mcp_servers=[
                McpServerConfig(
                    name="web-search",
                    transport=McpTransportType.HTTP,
                    url="http://localhost:3001/mcp",
                )
            ],
        )

        await create_agent_from_config(config, mcp_tool_loader=mcp_loader_with_tool)

        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        tools = kwargs["tools"]
        assert len(tools) == 2
        # First tool is the local one, second is MCP
        assert tools[1] is fake_mcp_tool

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_no_mcp_without_loader(self, mock_create):
        """When mcp_tool_loader is None, MCP configs are ignored."""
        mock_create.return_value = MagicMock()

        config = AgentConfig(
            name="no-loader-test",
            mcp_servers=[
                McpServerConfig(
                    name="filesystem",
                    transport=McpTransportType.STDIO,
                    command="npx",
                )
            ],
        )

        await create_agent_from_config(config, mcp_tool_loader=None)

        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        assert kwargs["tools"] is None

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_no_mcp_without_configs(self, mock_create):
        """When no mcp_servers configured, behavior is unchanged from before."""
        mock_create.return_value = MagicMock()
        mock_loader = AsyncMock(spec=McpToolLoader)
        mock_loader.load_tools.return_value = [MagicMock()]

        config = AgentConfig(name="no-mcp-test")

        await create_agent_from_config(config, mcp_tool_loader=mock_loader)

        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        assert kwargs["tools"] is None


class TestSubagentMcpIntegration:
    """Tests for MCP tool integration in subagent resolution."""

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_subagent_with_mcp_tools(self, mock_create):
        """Subagent MCP tools are loaded and passed correctly."""
        mock_create.return_value = MagicMock()
        fake_mcp_tool = MagicMock(name="subagent_mcp_tool")
        mock_loader = AsyncMock(spec=McpToolLoader)
        mock_loader.load_tools.return_value = [fake_mcp_tool]

        config = AgentConfig(
            name="parent-agent",
            subagents=[
                SubAgentConfig(
                    name="sub-with-mcp",
                    description="A sub-agent with MCP tools",
                    mcp_servers=[
                        McpServerConfig(
                            name="filesystem",
                            transport=McpTransportType.STDIO,
                            command="npx",
                        )
                    ],
                )
            ],
        )

        await create_agent_from_config(config, mcp_tool_loader=mock_loader)

        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        subagents = kwargs["subagents"]
        assert len(subagents) == 1
        assert subagents[0]["tools"] == [fake_mcp_tool]

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_subagent_merges_local_and_mcp_tools(self, mock_create):
        """Subagent local tools and MCP tools are merged."""
        mock_create.return_value = MagicMock()
        fake_mcp_tool = MagicMock(name="subagent_mcp_tool")
        mock_loader = AsyncMock(spec=McpToolLoader)
        mock_loader.load_tools.return_value = [fake_mcp_tool]

        config = AgentConfig(
            name="parent-agent",
            subagents=[
                SubAgentConfig(
                    name="sub-mixed",
                    description="Sub-agent with both tool types",
                    tools=["src.infrastructure.deepagent.example_tools:get_user_name"],
                    mcp_servers=[
                        McpServerConfig(
                            name="fs",
                            transport=McpTransportType.STDIO,
                            command="npx",
                        )
                    ],
                )
            ],
        )

        await create_agent_from_config(config, mcp_tool_loader=mock_loader)

        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        subagents = kwargs["subagents"]
        tools = subagents[0]["tools"]
        assert len(tools) == 2
        assert tools[1] is fake_mcp_tool

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_subagent_without_mcp_unchanged(self, mock_create):
        """Subagents without mcp_servers still work as before."""
        mock_create.return_value = MagicMock()
        mock_loader = AsyncMock(spec=McpToolLoader)
        mock_loader.load_tools.return_value = []

        config = AgentConfig(
            name="parent-agent",
            subagents=[
                SubAgentConfig(
                    name="plain-sub",
                    description="A plain sub-agent",
                )
            ],
        )

        await create_agent_from_config(config, mcp_tool_loader=mock_loader)

        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        subagents = kwargs["subagents"]
        assert subagents[0]["tools"] is None

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_subagent_mcp_ignored_without_loader(self, mock_create):
        """When mcp_tool_loader is None, subagent MCP configs are ignored."""
        mock_create.return_value = MagicMock()

        config = AgentConfig(
            name="parent-agent",
            subagents=[
                SubAgentConfig(
                    name="sub-no-loader",
                    description="Sub-agent with MCP but no loader",
                    mcp_servers=[
                        McpServerConfig(
                            name="fs",
                            transport=McpTransportType.STDIO,
                            command="npx",
                        )
                    ],
                )
            ],
        )

        await create_agent_from_config(config, mcp_tool_loader=None)

        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        subagents = kwargs["subagents"]
        assert subagents[0]["tools"] is None
