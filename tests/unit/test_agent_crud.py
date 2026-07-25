"""Tests for agent CRUD use cases.

Mocked external boundaries:
- AgentConfigStore (MinIO) -> mock_agent_config_store fixture
- AgentConfigRepository (PostgreSQL) -> mock_agent_config_repository fixture
- AgentRegistry (LangGraph) -> AsyncMock(spec=AgentRegistry)

Internal component used real:
- YamlAgentConfigLoader -> yaml_loader fixture (shared)
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
from src.domain.ports.agent_registry import AgentRegistry

VALID_YAML = (
    "name: test-agent\n"
    "model: claude-sonnet-4-5-20250929\n"
    'system_prompt: "You are a test agent."\n'
    "tools: []\n"
    "debug: false\n"
)

INVALID_YAML = ":::invalid yaml{{{}"


class TestCreateAgentConfigUseCase:
    """Tests for CreateAgentConfigUseCase."""

    @pytest.fixture
    def mock_registry(self):
        return AsyncMock(spec=AgentRegistry)

    @pytest.fixture
    def use_case(self, yaml_loader, mock_agent_config_store, mock_agent_config_repository):
        return CreateAgentConfigUseCase(
            config_loader=yaml_loader,
            config_store=mock_agent_config_store,
            config_repository=mock_agent_config_repository,
        )

    async def test_returns_config_with_provided_name_when_created(self, use_case, mock_agent_config_repository):
        """Should return parsed config with the provided name."""
        # Arrange
        mock_agent_config_repository.exists.return_value = False

        # Act
        result = await use_case.execute(name="test-agent", yaml_content=VALID_YAML)

        # Assert
        assert result.name == "test-agent"

    async def test_returns_config_with_parsed_model_when_created(self, use_case, mock_agent_config_repository):
        """Should return parsed config with the YAML model."""
        # Arrange
        mock_agent_config_repository.exists.return_value = False

        # Act
        result = await use_case.execute(name="test-agent", yaml_content=VALID_YAML)

        # Assert
        assert result.model == "claude-sonnet-4-5-20250929"

    async def test_returns_config_with_parsed_system_prompt_when_created(self, use_case, mock_agent_config_repository):
        """Should return parsed config with the YAML system_prompt."""
        # Arrange
        mock_agent_config_repository.exists.return_value = False

        # Act
        result = await use_case.execute(name="test-agent", yaml_content=VALID_YAML)

        # Assert
        assert result.system_prompt == "You are a test agent."

    async def test_checks_existence_with_repository_when_created(self, use_case, mock_agent_config_repository):
        """Should check existence on the repository with the agent name."""
        # Arrange
        mock_agent_config_repository.exists.return_value = False

        # Act
        await use_case.execute(name="test-agent", yaml_content=VALID_YAML)

        # Assert
        mock_agent_config_repository.exists.assert_awaited_once_with("test-agent")

    async def test_stores_yaml_in_store_when_created(
        self, use_case, mock_agent_config_repository, mock_agent_config_store
    ):
        """Should store the YAML in the config store."""
        # Arrange
        mock_agent_config_repository.exists.return_value = False

        # Act
        await use_case.execute(name="test-agent", yaml_content=VALID_YAML)

        # Assert
        mock_agent_config_store.put.assert_awaited_once()

    async def test_saves_metadata_in_repository_when_created(self, use_case, mock_agent_config_repository):
        """Should save metadata in the repository."""
        # Arrange
        mock_agent_config_repository.exists.return_value = False

        # Act
        await use_case.execute(name="test-agent", yaml_content=VALID_YAML)

        # Assert
        mock_agent_config_repository.save.assert_awaited_once()

    async def test_raises_already_exists_when_agent_present(self, use_case, mock_agent_config_repository):
        """Should raise AgentConfigAlreadyExistsError when agent already exists."""
        # Arrange
        mock_agent_config_repository.exists.return_value = True

        # Act & Assert
        with pytest.raises(AgentConfigAlreadyExistsError):
            await use_case.execute(name="test-agent", yaml_content=VALID_YAML)

    async def test_raises_config_error_when_yaml_invalid(self, use_case, mock_agent_config_repository):
        """Should raise ConfigError when YAML is invalid (via real loader)."""
        # Arrange
        mock_agent_config_repository.exists.return_value = False

        # Act & Assert
        with pytest.raises(ConfigError):
            await use_case.execute(name="bad-agent", yaml_content=INVALID_YAML)

    # ------------------------------------------------------------------
    # New: description persistence + agent_ref validation on create.
    # ------------------------------------------------------------------

    async def test_saves_description_in_metadata_when_present(
        self, use_case, mock_agent_config_repository, mock_agent_config_store
    ):
        """Should save the parsed description into the AgentConfigMetadata."""
        # Arrange
        mock_agent_config_repository.exists.return_value = False
        yaml_with_description = (
            "name: test-agent\n"
            "model: claude-sonnet-4-5-20250929\n"
            'system_prompt: "You are a test agent."\n'
            'description: "My agent"\n'
        )

        # Act
        await use_case.execute(name="test-agent", yaml_content=yaml_with_description)

        # Assert
        mock_agent_config_repository.save.assert_awaited_once()
        saved_metadata = mock_agent_config_repository.save.await_args.args[0]
        assert saved_metadata.description == "My agent"

    async def test_rejects_subagent_agent_ref_pointing_to_nonexistent_agent(
        self, use_case, mock_agent_config_repository, mock_agent_config_store
    ):
        """Should raise ConfigError when a subagent agent_ref does not exist."""
        # Arrange
        mock_agent_config_repository.exists.return_value = False

        async def exists_side_effect(name: str) -> bool:
            return False if name == "ghost" else False

        mock_agent_config_repository.exists.side_effect = exists_side_effect
        yaml_with_ref = (
            "name: parent-agent\n"
            "model: claude-sonnet-4-5-20250929\n"
            "subagents:\n"
            "  - name: sub\n"
            "    description: d\n"
            "    agent_ref: ghost\n"
        )

        # Act & Assert
        with pytest.raises(ConfigError):
            await use_case.execute(name="parent-agent", yaml_content=yaml_with_ref)
        mock_agent_config_store.put.assert_not_awaited()

    async def test_rejects_subagent_agent_ref_equal_to_agent_name(
        self, use_case, mock_agent_config_repository, mock_agent_config_store
    ):
        """Should raise ConfigError when a subagent agent_ref equals the agent's own name."""
        # Arrange
        mock_agent_config_repository.exists.return_value = False
        yaml_self_ref = (
            "name: self-agent\n"
            "model: claude-sonnet-4-5-20250929\n"
            "subagents:\n"
            "  - name: sub\n"
            "    description: d\n"
            "    agent_ref: self-agent\n"
        )

        # Act & Assert
        with pytest.raises(ConfigError):
            await use_case.execute(name="self-agent", yaml_content=yaml_self_ref)

    async def test_accepts_subagent_agent_ref_pointing_to_existing_agent(
        self, use_case, mock_agent_config_repository, mock_agent_config_store
    ):
        """Should succeed when subagent agent_ref points to an existing agent."""
        # Arrange
        existing_names = {"researcher"}

        async def exists_side_effect(name: str) -> bool:
            return name in existing_names

        mock_agent_config_repository.exists.side_effect = exists_side_effect
        yaml_with_ref = (
            "name: parent-agent\n"
            "model: claude-sonnet-4-5-20250929\n"
            "subagents:\n"
            "  - name: sub\n"
            "    description: d\n"
            "    agent_ref: researcher\n"
        )

        # Act
        await use_case.execute(name="parent-agent", yaml_content=yaml_with_ref)

        # Assert — the use case must have validated the referenced agent exists.
        mock_agent_config_store.put.assert_awaited_once()
        exists_calls = [call.args[0] for call in mock_agent_config_repository.exists.await_args_list]
        assert "researcher" in exists_calls


class TestUpdateAgentConfigUseCase:
    """Tests for UpdateAgentConfigUseCase."""

    @pytest.fixture
    def mock_registry(self):
        return AsyncMock(spec=AgentRegistry)

    @pytest.fixture
    def use_case(self, yaml_loader, mock_agent_config_store, mock_agent_config_repository, mock_registry):
        return UpdateAgentConfigUseCase(
            config_loader=yaml_loader,
            config_store=mock_agent_config_store,
            config_repository=mock_agent_config_repository,
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

    async def test_returns_config_with_provided_name_when_updated(
        self, use_case, mock_agent_config_repository, existing_metadata
    ):
        """Should return parsed config with the provided name."""
        # Arrange
        mock_agent_config_repository.get.return_value = existing_metadata

        # Act
        result = await use_case.execute(name="test-agent", yaml_content=VALID_YAML)

        # Assert
        assert result.name == "test-agent"

    async def test_stores_yaml_in_store_when_updated(
        self, use_case, mock_agent_config_repository, mock_agent_config_store, existing_metadata
    ):
        """Should store the YAML in the config store."""
        # Arrange
        mock_agent_config_repository.get.return_value = existing_metadata

        # Act
        await use_case.execute(name="test-agent", yaml_content=VALID_YAML)

        # Assert
        mock_agent_config_store.put.assert_awaited_once()

    async def test_saves_metadata_in_repository_when_updated(
        self, use_case, mock_agent_config_repository, existing_metadata
    ):
        """Should save metadata in the repository."""
        # Arrange
        mock_agent_config_repository.get.return_value = existing_metadata

        # Act
        await use_case.execute(name="test-agent", yaml_content=VALID_YAML)

        # Assert
        mock_agent_config_repository.save.assert_awaited_once()

    async def test_invalidates_registry_cache_when_updated(
        self, use_case, mock_agent_config_repository, mock_registry, existing_metadata
    ):
        """Should invalidate the registry cache for the agent."""
        # Arrange
        mock_agent_config_repository.get.return_value = existing_metadata

        # Act
        await use_case.execute(name="test-agent", yaml_content=VALID_YAML)

        # Assert
        mock_registry.invalidate.assert_awaited_once_with("test-agent")

    async def test_raises_not_found_when_agent_absent(self, use_case, mock_agent_config_repository):
        """Should raise AgentNotFoundError when agent does not exist."""
        # Arrange
        mock_agent_config_repository.get.side_effect = AgentNotFoundError("not found")

        # Act & Assert
        with pytest.raises(AgentNotFoundError):
            await use_case.execute(name="nonexistent", yaml_content=VALID_YAML)

    async def test_raises_config_error_when_name_mismatch(
        self, use_case, mock_agent_config_repository, existing_metadata
    ):
        """Should raise ConfigError when YAML name differs from name parameter."""
        # Arrange
        mock_agent_config_repository.get.return_value = existing_metadata
        mismatched_yaml = (
            'name: different-name\nmodel: claude-sonnet-4-5-20250929\nsystem_prompt: "You are a test agent."\n'
        )

        # Act & Assert
        with pytest.raises(ConfigError):
            await use_case.execute(name="test-agent", yaml_content=mismatched_yaml)

    # ------------------------------------------------------------------
    # New: description update + dependent agents invalidation on update.
    # ------------------------------------------------------------------

    async def test_updates_description_in_metadata(
        self, use_case, mock_agent_config_repository, existing_metadata
    ):
        """Should update the metadata description when the YAML provides one."""
        # Arrange
        mock_agent_config_repository.get.return_value = existing_metadata
        yaml_with_description = (
            "name: test-agent\n"
            "model: claude-sonnet-4-5-20250929\n"
            'system_prompt: "You are a test agent."\n'
            'description: "Updated description"\n'
        )

        # Act
        await use_case.execute(name="test-agent", yaml_content=yaml_with_description)

        # Assert
        mock_agent_config_repository.save.assert_awaited_once()
        saved_metadata = mock_agent_config_repository.save.await_args.args[0]
        assert saved_metadata.description == "Updated description"

    async def test_invalidates_dependent_agents_referencing_updated_agent(
        self, use_case, mock_agent_config_repository, mock_agent_config_store, mock_registry, yaml_loader
    ):
        """Should invalidate the updated agent AND dependents that reference it via agent_ref."""
        # Arrange
        # Agent "X" is being updated; agents "A" references X via subagent agent_ref; "B" does not.
        agent_a_yaml = (
            "name: A\n"
            "model: claude-sonnet-4-5-20250929\n"
            "subagents:\n"
            "  - name: sub\n"
            "    description: d\n"
            "    agent_ref: X\n"
        )
        agent_b_yaml = (
            "name: B\n"
            "model: claude-sonnet-4-5-20250929\n"
        )
        agent_x_yaml = (
            "name: X\n"
            "model: claude-sonnet-4-5-20250929\n"
            'system_prompt: "You are X."\n'
        )

        mock_agent_config_repository.get.return_value = AgentConfigMetadata(
            name="X",
            model="claude-sonnet-4-5-20250929",
            minio_path="agent-configs/X.yaml",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        async def list_all_side_effect():
            return ["A", "B"]

        async def store_get_side_effect(name: str) -> str:
            return {
                "A": agent_a_yaml,
                "B": agent_b_yaml,
                "X": agent_x_yaml,
            }[name]

        mock_agent_config_store.list_all.side_effect = list_all_side_effect
        mock_agent_config_store.get.side_effect = store_get_side_effect

        # Act
        await use_case.execute(name="X", yaml_content=agent_x_yaml)

        # Assert
        invalidated = [call.args[0] for call in mock_registry.invalidate.await_args_list]
        assert "X" in invalidated
        assert "A" in invalidated
        assert "B" not in invalidated


class TestDeleteAgentConfigUseCase:
    """Tests for DeleteAgentConfigUseCase."""

    @pytest.fixture
    def mock_registry(self):
        return AsyncMock(spec=AgentRegistry)

    @pytest.fixture
    def use_case(self, mock_agent_config_store, mock_agent_config_repository, mock_registry):
        return DeleteAgentConfigUseCase(
            config_store=mock_agent_config_store,
            config_repository=mock_agent_config_repository,
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

    async def test_deletes_from_store_when_deleted(
        self, use_case, mock_agent_config_repository, mock_agent_config_store, existing_metadata
    ):
        """Should delete the agent from the store."""
        # Arrange
        mock_agent_config_repository.get.return_value = existing_metadata

        # Act
        await use_case.execute(name="test-agent")

        # Assert
        mock_agent_config_store.delete.assert_awaited_once_with("test-agent")

    async def test_deletes_from_repository_when_deleted(
        self, use_case, mock_agent_config_repository, existing_metadata
    ):
        """Should delete the agent from the repository."""
        # Arrange
        mock_agent_config_repository.get.return_value = existing_metadata

        # Act
        await use_case.execute(name="test-agent")

        # Assert
        mock_agent_config_repository.delete.assert_awaited_once_with("test-agent")

    async def test_invalidates_registry_cache_when_deleted(
        self, use_case, mock_agent_config_repository, mock_registry, existing_metadata
    ):
        """Should invalidate the registry cache for the agent."""
        # Arrange
        mock_agent_config_repository.get.return_value = existing_metadata

        # Act
        await use_case.execute(name="test-agent")

        # Assert
        mock_registry.invalidate.assert_awaited_once_with("test-agent")

    async def test_raises_not_found_when_agent_absent(self, use_case, mock_agent_config_repository):
        """Should raise AgentNotFoundError when agent does not exist."""
        # Arrange
        mock_agent_config_repository.get.side_effect = AgentNotFoundError("not found")

        # Act & Assert
        with pytest.raises(AgentNotFoundError):
            await use_case.execute(name="nonexistent")

    # ------------------------------------------------------------------
    # New: dependent agents invalidation on delete.
    # ------------------------------------------------------------------

    async def test_invalidates_dependent_agents_referencing_deleted_agent(
        self, use_case, mock_agent_config_repository, mock_agent_config_store, mock_registry, yaml_loader
    ):
        """Should invalidate the deleted agent AND dependents that reference it via agent_ref."""
        # Arrange
        # Agent "X" is being deleted; agent "A" references X via subagent agent_ref; "B" does not.
        agent_a_yaml = (
            "name: A\n"
            "model: claude-sonnet-4-5-20250929\n"
            "subagents:\n"
            "  - name: sub\n"
            "    description: d\n"
            "    agent_ref: X\n"
        )
        agent_b_yaml = (
            "name: B\n"
            "model: claude-sonnet-4-5-20250929\n"
        )

        mock_agent_config_repository.get.return_value = AgentConfigMetadata(
            name="X",
            model="claude-sonnet-4-5-20250929",
            minio_path="agent-configs/X.yaml",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        async def list_all_side_effect():
            return ["A", "B"]

        async def store_get_side_effect(name: str) -> str:
            return {
                "A": agent_a_yaml,
                "B": agent_b_yaml,
            }[name]

        mock_agent_config_store.list_all.side_effect = list_all_side_effect
        mock_agent_config_store.get.side_effect = store_get_side_effect

        # Act
        await use_case.execute(name="X")

        # Assert
        invalidated = [call.args[0] for call in mock_registry.invalidate.await_args_list]
        assert "X" in invalidated
        assert "A" in invalidated
        assert "B" not in invalidated


class TestGetAgentConfigUseCase:
    """Tests for GetAgentConfigUseCase."""

    @pytest.fixture
    def use_case(self, yaml_loader, mock_agent_config_store):
        return GetAgentConfigUseCase(
            config_loader=yaml_loader,
            config_store=mock_agent_config_store,
        )

    async def test_returns_config_with_name_when_found(self, use_case, mock_agent_config_store):
        """Should return parsed config with the agent name."""
        # Arrange
        mock_agent_config_store.get.return_value = VALID_YAML

        # Act
        result = await use_case.execute(name="test-agent")

        # Assert
        assert result.name == "test-agent"

    async def test_returns_config_with_model_when_found(self, use_case, mock_agent_config_store):
        """Should return parsed config with the YAML model."""
        # Arrange
        mock_agent_config_store.get.return_value = VALID_YAML

        # Act
        result = await use_case.execute(name="test-agent")

        # Assert
        assert result.model == "claude-sonnet-4-5-20250929"

    async def test_returns_config_with_system_prompt_when_found(self, use_case, mock_agent_config_store):
        """Should return parsed config with the YAML system_prompt."""
        # Arrange
        mock_agent_config_store.get.return_value = VALID_YAML

        # Act
        result = await use_case.execute(name="test-agent")

        # Assert
        assert result.system_prompt == "You are a test agent."

    async def test_fetches_yaml_from_store_with_name(self, use_case, mock_agent_config_store):
        """Should fetch the YAML from the store with the agent name."""
        # Arrange
        mock_agent_config_store.get.return_value = VALID_YAML

        # Act
        await use_case.execute(name="test-agent")

        # Assert
        mock_agent_config_store.get.assert_awaited_once_with("test-agent")


class TestListAgentConfigsUseCase:
    """Tests for ListAgentConfigsUseCase."""

    @pytest.fixture
    def use_case(self, mock_agent_config_repository):
        return ListAgentConfigsUseCase(config_repository=mock_agent_config_repository)

    @pytest.fixture
    def two_metadatas(self):
        now = datetime.now(UTC)
        return [
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

    async def test_returns_two_entries_when_two_in_repository(
        self, use_case, mock_agent_config_repository, two_metadatas
    ):
        """Should return the list of metadatas from the repository."""
        # Arrange
        mock_agent_config_repository.list_all.return_value = two_metadatas

        # Act
        result = await use_case.execute()

        # Assert
        assert len(result) == 2

    async def test_returns_first_metadata_name(self, use_case, mock_agent_config_repository, two_metadatas):
        """Should preserve the order of the first metadata."""
        # Arrange
        mock_agent_config_repository.list_all.return_value = two_metadatas

        # Act
        result = await use_case.execute()

        # Assert
        assert result[0].name == "agent-a"

    async def test_returns_second_metadata_name(self, use_case, mock_agent_config_repository, two_metadatas):
        """Should preserve the order of the second metadata."""
        # Arrange
        mock_agent_config_repository.list_all.return_value = two_metadatas

        # Act
        result = await use_case.execute()

        # Assert
        assert result[1].name == "agent-b"

    async def test_queries_repository_when_executed(self, use_case, mock_agent_config_repository, two_metadatas):
        """Should call list_all on the repository."""
        # Arrange
        mock_agent_config_repository.list_all.return_value = two_metadatas

        # Act
        await use_case.execute()

        # Assert
        mock_agent_config_repository.list_all.assert_awaited_once()
