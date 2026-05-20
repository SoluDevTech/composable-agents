"""Tests for PersistentAgentRegistry.

Mocks AgentConfigStore, AgentConfigRepository, and create_agent_from_config (external).
Uses real YamlAgentConfigLoader (internal).
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.entities.agent_config_metadata import AgentConfigMetadata
from src.domain.ports.agent_config_repository import AgentConfigRepository
from src.domain.ports.agent_config_store import AgentConfigStore
from src.infrastructure.persistent_registry.adapter import PersistentAgentRegistry
from src.infrastructure.yaml_config.adapter import YamlAgentConfigLoader

VALID_YAML = (
    "name: test-agent\n"
    "model: claude-sonnet-4-5-20250929\n"
    'system_prompt: "You are a test agent."\n'
    "tools: []\n"
    "debug: false\n"
)


class TestPersistentAgentRegistry:
    @pytest.fixture
    def loader(self):
        """Real YamlAgentConfigLoader (internal implementation)."""
        return YamlAgentConfigLoader()

    @pytest.fixture
    def mock_store(self):
        """AsyncMock for the AgentConfigStore port (MinIO boundary)."""
        return AsyncMock(spec=AgentConfigStore)

    @pytest.fixture
    def mock_repository(self):
        """AsyncMock for the AgentConfigRepository port (PostgreSQL boundary)."""
        return AsyncMock(spec=AgentConfigRepository)

    @pytest.fixture
    def mock_mcp_tool_loader(self):
        """AsyncMock for the McpToolLoader port."""
        mock = AsyncMock()
        mock.load_tools.return_value = []
        return mock

    @pytest.fixture
    def registry(self, loader, mock_store, mock_repository, mock_mcp_tool_loader):
        return PersistentAgentRegistry(
            config_loader=loader,
            config_store=mock_store,
            config_repository=mock_repository,
            mcp_tool_loader=mock_mcp_tool_loader,
        )

    # -- get_runner --------------------------------------------------------

    @patch(
        "src.infrastructure.persistent_registry.adapter.create_agent_from_config",
        new_callable=AsyncMock,
    )
    @patch("src.infrastructure.persistent_registry.adapter.DeepAgentRunner")
    async def test_get_runner_loads_from_store(self, mock_runner_cls, mock_create, registry, mock_store):
        """get_runner should fetch YAML from MinIO, parse it, create agent, cache runner."""
        mock_store.get.return_value = VALID_YAML
        mock_graph = MagicMock()
        mock_create.return_value = (mock_graph, None)
        mock_runner_instance = MagicMock()
        mock_runner_cls.return_value = mock_runner_instance

        runner = await registry.get_runner("test-agent")

        assert runner is mock_runner_instance
        mock_store.get.assert_awaited_once_with("test-agent")
        mock_create.assert_awaited_once()

    @patch(
        "src.infrastructure.persistent_registry.adapter.create_agent_from_config",
        new_callable=AsyncMock,
    )
    @patch("src.infrastructure.persistent_registry.adapter.DeepAgentRunner")
    async def test_get_runner_cache_hit(self, mock_runner_cls, mock_create, registry, mock_store):
        """Second call should return cached runner without fetching from store again."""
        mock_store.get.return_value = VALID_YAML
        mock_create.return_value = (MagicMock(), None)
        mock_runner_instance = MagicMock()
        mock_runner_cls.return_value = mock_runner_instance

        first = await registry.get_runner("test-agent")
        second = await registry.get_runner("test-agent")

        assert first is second
        assert mock_store.get.await_count == 1, "Store should only be called once"

    # -- list_agents -------------------------------------------------------

    async def test_list_agents_queries_repository(self, registry, mock_repository):
        """list_agents should delegate to repository.list_all."""
        now = datetime.now(UTC)
        mock_repository.list_all.return_value = [
            AgentConfigMetadata(
                name="agent-a",
                model="gpt-4o",
                minio_path="agent-configs/agent-a.yaml",
                created_at=now,
                updated_at=now,
            ),
        ]

        await registry.list_agents()

        mock_repository.list_all.assert_awaited_once()

    # -- invalidate --------------------------------------------------------

    @patch(
        "src.infrastructure.persistent_registry.adapter.create_agent_from_config",
        new_callable=AsyncMock,
    )
    @patch("src.infrastructure.persistent_registry.adapter.DeepAgentRunner")
    async def test_invalidate_clears_cache(self, mock_runner_cls, mock_create, registry, mock_store):
        """After invalidate, next get_runner should re-fetch from store."""
        mock_store.get.return_value = VALID_YAML
        mock_create.return_value = (MagicMock(), None)
        runner_a = MagicMock()
        runner_b = MagicMock()
        mock_runner_cls.side_effect = [runner_a, runner_b]

        first = await registry.get_runner("test-agent")
        await registry.invalidate("test-agent")
        second = await registry.get_runner("test-agent")

        assert first is runner_a
        assert second is runner_b
        assert first is not second
        assert mock_store.get.await_count == 2, "Store should be called twice after invalidate"

    # -- close -------------------------------------------------------------

    @patch(
        "src.infrastructure.persistent_registry.adapter.create_agent_from_config",
        new_callable=AsyncMock,
    )
    @patch("src.infrastructure.persistent_registry.adapter.DeepAgentRunner")
    async def test_close_clears_all_runners(self, mock_runner_cls, mock_create, registry, mock_store):
        """close should empty the runners cache."""
        mock_store.get.return_value = VALID_YAML
        mock_create.return_value = (MagicMock(), None)
        mock_runner_cls.return_value = MagicMock()

        await registry.get_runner("test-agent")
        assert registry._runners, "Runner should be cached before close"

        await registry.close()
        assert registry._runners == {}, "Cache should be empty after close"
