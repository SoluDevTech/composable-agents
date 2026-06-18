"""Tests for agent CRUD use cases.

Mocks AgentConfigStore, AgentConfigRepository, and AgentRegistry (external boundaries).
Uses real YamlAgentConfigLoader (internal).
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from src.application.use_cases.create_agent_config import CreateAgentConfigUseCase
from src.application.use_cases.delete_agent_config import DeleteAgentConfigUseCase
from src.application.use_cases.get_agent_config import GetAgentConfigUseCase
from src.application.use_cases.list_agent_configs import ListAgentConfigsUseCase
from src.application.use_cases.update_agent_config import UpdateAgentConfigUseCase
from src.domain.entities.agent_config_metadata import AgentConfigMetadata
from src.domain.errors.agent import AgentConfigAlreadyExistsError, AgentNotFoundError
from src.domain.errors.config import ConfigError
from src.domain.ports.agent_config_repository import AgentConfigRepository
from src.domain.ports.agent_config_store import AgentConfigStore
from src.domain.ports.agent_registry import AgentRegistry
from src.infrastructure.yaml_config.adapter import YamlAgentConfigLoader

VALID_YAML = (
    "name: test-agent\n"
    "model: claude-sonnet-4-5-20250929\n"
    'system_prompt: "You are a test agent."\n'
    "tools: []\n"
    "debug: false\n"
)

INVALID_YAML = ":::invalid yaml{{{}"

YAML_WITH_PROMPT_FILE = 'name: test-agent\nsystem_prompt_file: "./prompt.md"\n'


class TestCreateAgentConfigUseCase:
    """Tests for CreateAgentConfigUseCase."""

    @pytest.fixture
    def loader(self):
        return YamlAgentConfigLoader()

    @pytest.fixture
    def mock_store(self):
        return AsyncMock(spec=AgentConfigStore)

    @pytest.fixture
    def mock_repository(self):
        return AsyncMock(spec=AgentConfigRepository)

    @pytest.fixture
    def use_case(self, loader, mock_store, mock_repository):
        return CreateAgentConfigUseCase(
            config_loader=loader,
            config_store=mock_store,
            config_repository=mock_repository,
        )

    async def test_create_agent_success(self, use_case, mock_store, mock_repository):
        """Should parse YAML, check not exists, store in MinIO, save in PG, return AgentConfig."""
        mock_repository.exists.return_value = False

        result = await use_case.execute(name="test-agent", yaml_content=VALID_YAML)

        assert result.name == "test-agent"
        assert result.model == "claude-sonnet-4-5-20250929"
        assert result.system_prompt == "You are a test agent."
        mock_repository.exists.assert_awaited_once_with("test-agent")
        mock_store.put.assert_awaited_once()
        mock_repository.save.assert_awaited_once()

    async def test_create_agent_already_exists(self, use_case, mock_repository):
        """Should raise AgentConfigAlreadyExistsError when agent already in repository."""
        mock_repository.exists.return_value = True

        with pytest.raises(AgentConfigAlreadyExistsError):
            await use_case.execute(name="test-agent", yaml_content=VALID_YAML)

    async def test_create_agent_invalid_yaml(self, use_case, mock_repository):
        """Should raise ConfigError when YAML is invalid (via real loader)."""
        mock_repository.exists.return_value = False

        with pytest.raises(ConfigError):
            await use_case.execute(name="bad-agent", yaml_content=INVALID_YAML)


class TestUpdateAgentConfigUseCase:
    """Tests for UpdateAgentConfigUseCase."""

    @pytest.fixture
    def loader(self):
        return YamlAgentConfigLoader()

    @pytest.fixture
    def mock_store(self):
        return AsyncMock(spec=AgentConfigStore)

    @pytest.fixture
    def mock_repository(self):
        return AsyncMock(spec=AgentConfigRepository)

    @pytest.fixture
    def mock_registry(self):
        return AsyncMock(spec=AgentRegistry)

    @pytest.fixture
    def use_case(self, loader, mock_store, mock_repository, mock_registry):
        return UpdateAgentConfigUseCase(
            config_loader=loader,
            config_store=mock_store,
            config_repository=mock_repository,
            agent_registry=mock_registry,
        )

    @pytest.fixture
    def existing_metadata(self):
        now = datetime.now(UTC)
        return AgentConfigMetadata(
            name="test-agent",
            model="claude-sonnet-4-5-20250929",
            minio_path="agent-configs/test-agent.yaml",
            created_at=now,
            updated_at=now,
        )

    async def test_update_agent_success(self, use_case, mock_store, mock_repository, mock_registry, existing_metadata):
        """Should parse YAML, check exists, store, save, invalidate cache."""
        mock_repository.get.return_value = existing_metadata

        result = await use_case.execute(name="test-agent", yaml_content=VALID_YAML)

        assert result.name == "test-agent"
        mock_store.put.assert_awaited_once()
        mock_repository.save.assert_awaited_once()
        mock_registry.invalidate.assert_awaited_once_with("test-agent")

    async def test_update_agent_not_found(self, use_case, mock_repository):
        """Should raise AgentNotFoundError when agent does not exist in repository."""
        mock_repository.get.side_effect = AgentNotFoundError("not found")

        with pytest.raises(AgentNotFoundError):
            await use_case.execute(name="nonexistent", yaml_content=VALID_YAML)

    async def test_update_agent_name_mismatch(self, use_case, mock_repository, existing_metadata):
        """Should raise ConfigError when name in YAML does not match name parameter."""
        mock_repository.get.return_value = existing_metadata
        mismatched_yaml = (
            'name: different-name\nmodel: claude-sonnet-4-5-20250929\nsystem_prompt: "You are a test agent."\n'
        )

        with pytest.raises(ConfigError):
            await use_case.execute(name="test-agent", yaml_content=mismatched_yaml)


class TestDeleteAgentConfigUseCase:
    """Tests for DeleteAgentConfigUseCase."""

    @pytest.fixture
    def mock_store(self):
        return AsyncMock(spec=AgentConfigStore)

    @pytest.fixture
    def mock_repository(self):
        return AsyncMock(spec=AgentConfigRepository)

    @pytest.fixture
    def mock_registry(self):
        return AsyncMock(spec=AgentRegistry)

    @pytest.fixture
    def use_case(self, mock_store, mock_repository, mock_registry):
        return DeleteAgentConfigUseCase(
            config_store=mock_store,
            config_repository=mock_repository,
            agent_registry=mock_registry,
        )

    @pytest.fixture
    def existing_metadata(self):
        now = datetime.now(UTC)
        return AgentConfigMetadata(
            name="test-agent",
            model="claude-sonnet-4-5-20250929",
            minio_path="agent-configs/test-agent.yaml",
            created_at=now,
            updated_at=now,
        )

    async def test_delete_agent_success(self, use_case, mock_store, mock_repository, mock_registry, existing_metadata):
        """Should delete from MinIO and PG, then invalidate cache."""
        mock_repository.get.return_value = existing_metadata

        await use_case.execute(name="test-agent")

        mock_store.delete.assert_awaited_once_with("test-agent")
        mock_repository.delete.assert_awaited_once_with("test-agent")
        mock_registry.invalidate.assert_awaited_once_with("test-agent")

    async def test_delete_agent_not_found(self, use_case, mock_repository):
        """Should raise AgentNotFoundError when agent does not exist."""
        mock_repository.get.side_effect = AgentNotFoundError("not found")

        with pytest.raises(AgentNotFoundError):
            await use_case.execute(name="nonexistent")


class TestGetAgentConfigUseCase:
    """Tests for GetAgentConfigUseCase."""

    @pytest.fixture
    def loader(self):
        return YamlAgentConfigLoader()

    @pytest.fixture
    def mock_store(self):
        return AsyncMock(spec=AgentConfigStore)

    @pytest.fixture
    def use_case(self, loader, mock_store):
        return GetAgentConfigUseCase(
            config_loader=loader,
            config_store=mock_store,
        )

    async def test_get_agent_success(self, use_case, mock_store):
        """Should fetch YAML from store, parse via real loader, return AgentConfig."""
        mock_store.get.return_value = VALID_YAML

        result = await use_case.execute(name="test-agent")

        assert result.name == "test-agent"
        assert result.model == "claude-sonnet-4-5-20250929"
        assert result.system_prompt == "You are a test agent."
        mock_store.get.assert_awaited_once_with("test-agent")


class TestListAgentConfigsUseCase:
    """Tests for ListAgentConfigsUseCase."""

    @pytest.fixture
    def mock_repository(self):
        return AsyncMock(spec=AgentConfigRepository)

    @pytest.fixture
    def use_case(self, mock_repository):
        return ListAgentConfigsUseCase(config_repository=mock_repository)

    async def test_list_agents_returns_metadata(self, use_case, mock_repository):
        """Should query repository and return list of AgentConfigMetadata."""
        now = datetime.now(UTC)
        mock_repository.list_all.return_value = [
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

        result = await use_case.execute()

        assert len(result) == 2
        assert result[0].name == "agent-a"
        assert result[1].name == "agent-b"
        mock_repository.list_all.assert_awaited_once()
