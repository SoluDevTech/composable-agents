"""Tests for McpServerConfig domain entity."""

import pytest
from pydantic import ValidationError

from src.domain.entities.agent_config import AgentConfig
from src.domain.entities.mcp_server_config import McpServerConfig, McpTransportType


class TestMcpServerConfig:
    def test_stdio_config_valid(self):
        config = McpServerConfig(
            name="filesystem",
            transport=McpTransportType.STDIO,
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem"],
        )
        assert config.transport == McpTransportType.STDIO
        assert config.command == "npx"

    def test_http_config_valid(self):
        config = McpServerConfig(
            name="web-search",
            transport=McpTransportType.HTTP,
            url="http://localhost:3001/mcp",
            headers={"Authorization": "Bearer ${TOKEN}"},
        )
        assert config.url == "http://localhost:3001/mcp"

    def test_stdio_without_command_raises(self):
        with pytest.raises(ValueError, match="command.*required"):
            McpServerConfig(name="bad", transport=McpTransportType.STDIO)

    def test_http_without_url_raises(self):
        with pytest.raises(ValueError, match="url.*required"):
            McpServerConfig(name="bad", transport=McpTransportType.HTTP)

    def test_frozen_immutability(self):
        config = McpServerConfig(name="test", transport=McpTransportType.STDIO, command="echo")
        with pytest.raises(ValidationError):
            config.name = "changed"


class TestAgentConfigWithMcp:
    def test_agent_config_with_mcp_servers(self):
        config = AgentConfig(
            name="test",
            mcp_servers=[
                McpServerConfig(name="fs", transport="stdio", command="npx", args=[]),
            ],
        )
        assert len(config.mcp_servers) == 1
        assert config.mcp_servers[0].name == "fs"

    def test_agent_config_defaults_empty_mcp(self):
        config = AgentConfig(name="test")
        assert config.mcp_servers == []
