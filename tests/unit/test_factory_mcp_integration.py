"""Tests for MCP tool integration in create_agent_from_config.

Patches ``create_deep_agent`` (external LLM factory).
Uses the shared ``mock_mcp_tool_loader`` fixture from external.py.
"""

from unittest.mock import MagicMock, patch

from src.domain.entities.agent_config import AgentConfig, SubAgentConfig
from src.domain.entities.mcp_server_config import McpServerConfig, McpTransportType
from src.infrastructure.deepagent.factory import create_agent_from_config

STDIO_CONFIG = McpServerConfig(
    name="filesystem",
    transport=McpTransportType.STDIO,
    command="npx",
    args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
)
HTTP_CONFIG = McpServerConfig(
    name="web-search",
    transport=McpTransportType.HTTP,
    url="http://localhost:3001/mcp",
)


class TestFactoryMcpIntegration:
    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_loads_mcp_tools_when_configs_present(self, mock_create, mock_mcp_tool_loader):
        # Arrange
        mock_create.return_value = MagicMock()
        fake_tool = MagicMock(name="mcp_read_file")
        mock_mcp_tool_loader.load_tools.return_value = [fake_tool]
        config = AgentConfig(name="mcp-test", mcp_servers=[STDIO_CONFIG])

        # Act
        await create_agent_from_config(config, mcp_tool_loader=mock_mcp_tool_loader)

        # Assert
        kwargs = mock_create.call_args.kwargs
        assert kwargs["tools"] == [fake_tool]

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_merges_local_and_mcp_tools(self, mock_create, mock_mcp_tool_loader):
        # Arrange
        mock_create.return_value = MagicMock()
        fake_mcp_tool = MagicMock(name="mcp_search")
        mock_mcp_tool_loader.load_tools.return_value = [fake_mcp_tool]
        config = AgentConfig(
            name="merged-tools-test",
            tools=["src.infrastructure.deepagent.example_tools:get_user_name"],
            mcp_servers=[HTTP_CONFIG],
        )

        # Act
        await create_agent_from_config(config, mcp_tool_loader=mock_mcp_tool_loader)

        # Assert
        kwargs = mock_create.call_args.kwargs
        tools = kwargs["tools"]
        assert len(tools) == 2
        assert tools[1] is fake_mcp_tool

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_no_mcp_without_loader(self, mock_create):
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(
            name="no-loader-test",
            mcp_servers=[McpServerConfig(name="filesystem", transport=McpTransportType.STDIO, command="npx")],
        )

        # Act
        await create_agent_from_config(config, mcp_tool_loader=None)

        # Assert
        kwargs = mock_create.call_args.kwargs
        assert kwargs["tools"] is None

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_no_mcp_without_configs(self, mock_create, mock_mcp_tool_loader):
        # Arrange
        mock_create.return_value = MagicMock()
        mock_mcp_tool_loader.load_tools.return_value = [MagicMock()]
        config = AgentConfig(name="no-mcp-test")

        # Act
        await create_agent_from_config(config, mcp_tool_loader=mock_mcp_tool_loader)

        # Assert
        kwargs = mock_create.call_args.kwargs
        assert kwargs["tools"] is None


class TestSubagentMcpIntegration:
    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_subagent_with_mcp_tools(self, mock_create, mock_mcp_tool_loader):
        # Arrange
        mock_create.return_value = MagicMock()
        fake_mcp_tool = MagicMock(name="subagent_mcp_tool")
        mock_mcp_tool_loader.load_tools.return_value = [fake_mcp_tool]
        config = AgentConfig(
            name="parent-agent",
            subagents=[
                SubAgentConfig(
                    name="sub-with-mcp",
                    description="A sub-agent with MCP tools",
                    mcp_servers=[McpServerConfig(name="filesystem", transport=McpTransportType.STDIO, command="npx")],
                )
            ],
        )

        # Act
        await create_agent_from_config(config, mcp_tool_loader=mock_mcp_tool_loader)

        # Assert
        kwargs = mock_create.call_args.kwargs
        subagents = kwargs["subagents"]
        assert len(subagents) == 1
        assert subagents[0]["tools"] == [fake_mcp_tool]

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_subagent_merges_local_and_mcp_tools(self, mock_create, mock_mcp_tool_loader):
        # Arrange
        mock_create.return_value = MagicMock()
        fake_mcp_tool = MagicMock(name="subagent_mcp_tool")
        mock_mcp_tool_loader.load_tools.return_value = [fake_mcp_tool]
        config = AgentConfig(
            name="parent-agent",
            subagents=[
                SubAgentConfig(
                    name="sub-mixed",
                    description="Sub-agent with both tool types",
                    tools=["src.infrastructure.deepagent.example_tools:get_user_name"],
                    mcp_servers=[McpServerConfig(name="fs", transport=McpTransportType.STDIO, command="npx")],
                )
            ],
        )

        # Act
        await create_agent_from_config(config, mcp_tool_loader=mock_mcp_tool_loader)

        # Assert
        kwargs = mock_create.call_args.kwargs
        subagents = kwargs["subagents"]
        tools = subagents[0]["tools"]
        assert len(tools) == 2
        assert tools[1] is fake_mcp_tool

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_subagent_without_mcp_unchanged(self, mock_create, mock_mcp_tool_loader):
        # Arrange
        mock_create.return_value = MagicMock()
        mock_mcp_tool_loader.load_tools.return_value = []
        config = AgentConfig(
            name="parent-agent",
            subagents=[SubAgentConfig(name="plain-sub", description="A plain sub-agent")],
        )

        # Act
        await create_agent_from_config(config, mcp_tool_loader=mock_mcp_tool_loader)

        # Assert
        kwargs = mock_create.call_args.kwargs
        subagents = kwargs["subagents"]
        assert subagents[0]["tools"] is None

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_subagent_mcp_ignored_without_loader(self, mock_create):
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(
            name="parent-agent",
            subagents=[
                SubAgentConfig(
                    name="sub-no-loader",
                    description="Sub-agent with MCP but no loader",
                    mcp_servers=[McpServerConfig(name="fs", transport=McpTransportType.STDIO, command="npx")],
                )
            ],
        )

        # Act
        await create_agent_from_config(config, mcp_tool_loader=None)

        # Assert
        kwargs = mock_create.call_args.kwargs
        subagents = kwargs["subagents"]
        assert subagents[0]["tools"] is None
