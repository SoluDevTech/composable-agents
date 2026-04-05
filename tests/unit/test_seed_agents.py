"""Tests for SeedAgentsUseCase.

Mocks AgentConfigStore and AgentConfigRepository (external boundaries).
Uses real YamlAgentConfigLoader (internal).
"""

from unittest.mock import AsyncMock

import pytest

from src.application.use_cases.seed_agents import SeedAgentsUseCase
from src.domain.ports.agent_config_repository import AgentConfigRepository
from src.domain.ports.agent_config_store import AgentConfigStore
from src.infrastructure.yaml_config.adapter import YamlAgentConfigLoader


class TestSeedAgentsUseCase:
    """Tests for SeedAgentsUseCase."""

    @pytest.fixture
    def loader(self):
        """Real YamlAgentConfigLoader (internal)."""
        return YamlAgentConfigLoader()

    @pytest.fixture
    def mock_store(self):
        return AsyncMock(spec=AgentConfigStore)

    @pytest.fixture
    def mock_repository(self):
        return AsyncMock(spec=AgentConfigRepository)

    @pytest.fixture
    def use_case(self, loader, mock_store, mock_repository):
        return SeedAgentsUseCase(
            config_loader=loader,
            config_store=mock_store,
            config_repository=mock_repository,
        )

    @pytest.fixture
    def agents_dir(self, tmp_path):
        """Create a temporary agents directory with seed YAML files."""
        d = tmp_path / "agents"
        d.mkdir()
        (d / "chatbot.yaml").write_text(
            'name: chatbot\nmodel: claude-sonnet-4-5-20250929\nsystem_prompt: "You are a chatbot."\n'
        )
        (d / "coder.yaml").write_text(
            'name: coder\nmodel: claude-sonnet-4-5-20250929\nsystem_prompt: "You are a coding assistant."\n'
        )
        return d

    async def test_seed_uploads_new_agents(self, use_case, mock_store, mock_repository, agents_dir):
        """For each YAML file not in PG, should upload to MinIO and save metadata."""
        mock_repository.exists.return_value = False

        await use_case.execute(agents_dir=agents_dir)

        # Both agents should be uploaded since neither exists
        assert mock_store.put.await_count == 2
        assert mock_repository.save.await_count == 2

    async def test_seed_skips_existing_agents(self, use_case, mock_store, mock_repository, agents_dir):
        """If agent already exists in PG, should not upload to MinIO."""
        # chatbot exists, coder does not
        mock_repository.exists.side_effect = lambda name: name == "chatbot"

        await use_case.execute(agents_dir=agents_dir)

        # Only coder should be uploaded
        assert mock_store.put.await_count == 1
        assert mock_repository.save.await_count == 1
        put_call_path = mock_store.put.call_args[0][0]
        assert put_call_path == "coder.yaml"

    async def test_seed_inlines_system_prompt_file(self, use_case, mock_store, mock_repository, tmp_path):
        """If YAML references system_prompt_file, should read it and inline the prompt before uploading."""
        d = tmp_path / "agents_with_prompt"
        d.mkdir()
        prompt_file = d / "prompt.md"
        prompt_file.write_text("You are a specialized agent with inlined prompt.")
        (d / "prompted-agent.yaml").write_text('name: prompted-agent\nsystem_prompt_file: "./prompt.md"\n')
        mock_repository.exists.return_value = False

        await use_case.execute(agents_dir=d)

        mock_store.put.assert_awaited_once()
        # The uploaded YAML content should have the prompt inlined (no system_prompt_file reference)
        uploaded_content = mock_store.put.call_args[0][1]
        assert "system_prompt_file" not in uploaded_content
        assert "You are a specialized agent with inlined prompt." in uploaded_content
