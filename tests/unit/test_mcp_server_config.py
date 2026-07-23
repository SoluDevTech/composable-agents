"""Tests for McpServerConfig domain entity (pure domain, no mocks)."""

import pytest
from pydantic import ValidationError

from src.domain.entities.agent_config import AgentConfig
from src.domain.entities.mcp_server_config import McpServerConfig, McpTransportType


class TestMcpServerConfig:
    def test_stdio_config_sets_transport(self):
        # Arrange
        # Act
        config = McpServerConfig(
            name="filesystem",
            transport=McpTransportType.STDIO,
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem"],
        )

        # Assert
        assert config.transport == McpTransportType.STDIO

    def test_stdio_config_sets_command(self):
        # Arrange
        # Act
        config = McpServerConfig(
            name="filesystem",
            transport=McpTransportType.STDIO,
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem"],
        )

        # Assert
        assert config.command == "npx"

    def test_http_config_sets_url(self):
        # Arrange
        # Act
        config = McpServerConfig(
            name="web-search",
            transport=McpTransportType.HTTP,
            url="http://localhost:3001/mcp",
            headers={"Authorization": "Bearer ${TOKEN}"},
        )

        # Assert
        assert config.url == "http://localhost:3001/mcp"

    def test_stdio_without_command_raises(self):
        # Arrange
        # Act & Assert
        with pytest.raises(ValueError, match="command.*required"):
            McpServerConfig(name="bad", transport=McpTransportType.STDIO)

    def test_http_without_url_raises(self):
        # Arrange
        # Act & Assert
        with pytest.raises(ValueError, match="url.*required"):
            McpServerConfig(name="bad", transport=McpTransportType.HTTP)

    def test_frozen_immutability_blocks_assignment(self):
        # Arrange
        config = McpServerConfig(name="test", transport=McpTransportType.STDIO, command="echo")

        # Act & Assert
        with pytest.raises(ValidationError):
            config.name = "changed"

    def test_http_config_with_auth_token(self):
        # Arrange
        # Act
        config = McpServerConfig(
            name="auth-server",
            transport=McpTransportType.HTTP,
            url="http://localhost:3001/mcp",
            auth_token="secret-token",
        )

        # Assert
        assert config.auth_token == "secret-token"


class TestAgentConfigWithMcp:
    def test_agent_config_stores_mcp_servers(self):
        # Arrange
        # Act
        config = AgentConfig(
            name="test",
            mcp_servers=[
                McpServerConfig(name="fs", transport="stdio", command="npx", args=[]),
            ],
        )

        # Assert
        assert len(config.mcp_servers) == 1
        assert config.mcp_servers[0].name == "fs"

    def test_agent_config_defaults_to_empty_mcp(self):
        # Arrange
        # Act
        config = AgentConfig(name="test")

        # Assert
        assert config.mcp_servers == []
