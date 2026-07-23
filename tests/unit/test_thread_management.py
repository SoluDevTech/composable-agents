"""Tests for thread management use cases.

Uses real internal components:
- PostgresThreadRepository (via shared thread_repo fixture, in-memory SQLite)
- YamlAgentConfigLoader (via shared yaml_loader fixture)
- PersistentAgentRegistry built from real yaml_loader + shared external mocks

External boundaries mocked via shared fixtures from tests/fixtures/external.py:
- mock_agent_config_store (MinIO)
- mock_agent_config_repository (PostgreSQL)
- mock_mcp_tool_loader (MCP server)
"""

from datetime import UTC, datetime

import pytest

from src.application.use_cases.create_thread import CreateThreadUseCase
from src.application.use_cases.delete_thread import DeleteThreadUseCase
from src.application.use_cases.get_thread import GetThreadUseCase
from src.application.use_cases.list_threads import ListThreadsUseCase
from src.domain.entities.agent_config_metadata import AgentConfigMetadata
from src.domain.errors.agent import AgentNotFoundError
from src.domain.errors.thread import ThreadNotFoundError
from src.infrastructure.persistent_registry.adapter import PersistentAgentRegistry

VALID_YAML = 'name: test-agent\nmodel: test-model\nsystem_prompt: "Test."\ntools: []\ndebug: false\n'


class TestCreateThreadUseCase:
    """Tests for CreateThreadUseCase."""

    @pytest.fixture
    def mock_agent_config_store_with_yaml(self, mock_agent_config_store):
        mock_agent_config_store.get.return_value = VALID_YAML
        return mock_agent_config_store

    @pytest.fixture
    def mock_agent_config_repository_with_metadata(self, mock_agent_config_repository):
        now = datetime.now(UTC)
        mock_agent_config_repository.list_all.return_value = [
            AgentConfigMetadata(
                name="test-agent",
                model="test-model",
                minio_path="test-agent.yaml",
                created_at=now,
                updated_at=now,
            )
        ]
        return mock_agent_config_repository

    @pytest.fixture
    def registry(
        self,
        yaml_loader,
        mock_agent_config_store_with_yaml,
        mock_agent_config_repository_with_metadata,
        mock_mcp_tool_loader,
    ):
        return PersistentAgentRegistry(
            config_loader=yaml_loader,
            config_store=mock_agent_config_store_with_yaml,
            config_repository=mock_agent_config_repository_with_metadata,
            mcp_tool_loader=mock_mcp_tool_loader,
        )

    @pytest.fixture
    def use_case(self, thread_repo, registry):
        return CreateThreadUseCase(thread_repo, registry)

    async def test_creates_thread_with_agent_name(self, use_case):
        """Should create a thread with the agent name."""
        # Arrange
        # Act
        thread = await use_case.execute("test-agent")

        # Assert
        assert thread.agent_name == "test-agent"

    async def test_creates_thread_with_id(self, use_case):
        """Should generate a non-None thread id."""
        # Arrange
        # Act
        thread = await use_case.execute("test-agent")

        # Assert
        assert thread.id is not None

    async def test_raises_when_agent_not_found(self, use_case, mock_agent_config_store_with_yaml):
        """Should raise AgentNotFoundError when the agent is unknown."""
        # Arrange
        mock_agent_config_store_with_yaml.get.side_effect = AgentNotFoundError("not found")

        # Act & Assert
        with pytest.raises(AgentNotFoundError):
            await use_case.execute("nonexistent-agent")


class TestGetThreadUseCase:
    """Tests for GetThreadUseCase."""

    @pytest.fixture
    def use_case(self, thread_repo):
        return GetThreadUseCase(thread_repo)

    async def test_returns_thread_with_matching_id(self, use_case, thread_repo):
        """Should return the thread matching the provided id."""
        # Arrange
        created = await thread_repo.create("test-agent")

        # Act
        thread = await use_case.execute(created.id)

        # Assert
        assert thread.id == created.id

    async def test_raises_when_thread_not_found(self, use_case):
        """Should raise ThreadNotFoundError when the thread does not exist."""
        # Arrange
        # Act & Assert
        with pytest.raises(ThreadNotFoundError):
            await use_case.execute("nonexistent-id")


class TestListThreadsUseCase:
    """Tests for ListThreadsUseCase."""

    @pytest.fixture
    def use_case(self, thread_repo):
        return ListThreadsUseCase(thread_repo)

    async def test_returns_all_threads(self, use_case, thread_repo):
        """Should return all threads in the repository."""
        # Arrange
        await thread_repo.create("agent-1")
        await thread_repo.create("agent-2")

        # Act
        result = await use_case.execute()

        # Assert
        assert len(result) == 2


class TestDeleteThreadUseCase:
    """Tests for DeleteThreadUseCase."""

    @pytest.fixture
    def use_case(self, thread_repo):
        return DeleteThreadUseCase(thread_repo)

    async def test_deletes_thread_so_get_raises(self, use_case, thread_repo):
        """Should delete the thread so it is no longer retrievable."""
        # Arrange
        created = await thread_repo.create("test-agent")

        # Act
        await use_case.execute(created.id)

        # Assert
        with pytest.raises(ThreadNotFoundError):
            await thread_repo.get(created.id)
