"""Tests for PersistentAgentRegistry.

Uses real YamlAgentConfigLoader and real NoopTracingProvider (internal).
Mocks external boundaries: mock_agent_config_store (MinIO),
mock_agent_config_repository (PostgreSQL), mock_mcp_tool_loader (MCP).
Patches create_agent_from_config to return a fake graph (LangGraph boundary).
The DeepAgentRunner is built for real.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.entities.agent_config_metadata import AgentConfigMetadata
from src.infrastructure.persistent_registry.adapter import PersistentAgentRegistry

VALID_YAML = (
    "name: test-agent\n"
    "model: claude-sonnet-4-5-20250929\n"
    'system_prompt: "You are a test agent."\n'
    "tools: []\n"
    "debug: false\n"
)


class TestPersistentAgentRegistry:
    @pytest.fixture
    def registry(self, yaml_loader, mock_agent_config_store, mock_agent_config_repository, mock_mcp_tool_loader):
        return PersistentAgentRegistry(
            config_loader=yaml_loader,
            config_store=mock_agent_config_store,
            config_repository=mock_agent_config_repository,
            mcp_tool_loader=mock_mcp_tool_loader,
        )

    @patch("src.infrastructure.persistent_registry.adapter.create_agent_from_config", new_callable=AsyncMock)
    async def test_get_runner_returns_real_runner(self, mock_create, registry, mock_agent_config_store):
        # Arrange
        mock_agent_config_store.get.return_value = VALID_YAML
        mock_create.return_value = (MagicMock(), None)

        # Act
        runner = await registry.get_runner("test-agent")

        # Assert
        mock_agent_config_store.get.assert_awaited_once_with("test-agent")
        mock_create.assert_awaited_once()
        assert runner is not None

    @patch("src.infrastructure.persistent_registry.adapter.create_agent_from_config", new_callable=AsyncMock)
    async def test_get_runner_cache_hit_returns_same_instance(self, mock_create, registry, mock_agent_config_store):
        # Arrange
        mock_agent_config_store.get.return_value = VALID_YAML
        mock_create.return_value = (MagicMock(), None)

        # Act
        first = await registry.get_runner("test-agent")
        second = await registry.get_runner("test-agent")

        # Assert
        assert first is second
        assert mock_agent_config_store.get.await_count == 1

    async def test_list_agents_returns_names_from_repository(self, registry, mock_agent_config_repository):
        # Arrange
        now = datetime.now(UTC)
        mock_agent_config_repository.list_all.return_value = [
            AgentConfigMetadata(
                name="agent-a",
                model="gpt-4o",
                minio_path="agent-configs/agent-a.yaml",
                created_at=now,
                updated_at=now,
            ),
            AgentConfigMetadata(
                name="agent-b",
                model="claude-sonnet-4-5-20250929",
                minio_path="agent-configs/agent-b.yaml",
                created_at=now,
                updated_at=now,
            ),
        ]

        # Act
        result = await registry.list_agents()

        # Assert
        assert result == ["agent-a", "agent-b"]
        mock_agent_config_repository.list_all.assert_awaited_once()

    @patch("src.infrastructure.persistent_registry.adapter.create_agent_from_config", new_callable=AsyncMock)
    async def test_invalidate_forces_rebuild_on_next_get(self, mock_create, registry, mock_agent_config_store):
        # Arrange
        mock_agent_config_store.get.return_value = VALID_YAML
        mock_create.side_effect = [(MagicMock(), None), (MagicMock(), None)]

        # Act
        first = await registry.get_runner("test-agent")
        await registry.invalidate("test-agent")
        second = await registry.get_runner("test-agent")

        # Assert
        assert first is not second
        assert mock_agent_config_store.get.await_count == 2

    @patch("src.infrastructure.persistent_registry.adapter.create_agent_from_config", new_callable=AsyncMock)
    async def test_close_forces_rebuild_on_next_get(self, mock_create, registry, mock_agent_config_store):
        # Arrange
        mock_agent_config_store.get.return_value = VALID_YAML
        mock_create.side_effect = [(MagicMock(), None), (MagicMock(), None)]

        # Act
        first = await registry.get_runner("test-agent")
        await registry.close()
        second = await registry.get_runner("test-agent")

        # Assert
        assert first is not second
        assert mock_agent_config_store.get.await_count == 2
