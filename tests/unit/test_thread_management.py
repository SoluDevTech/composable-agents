"""Tests for thread management use cases.

Uses real InMemoryThreadRepository (internal).
Uses AsyncMock for AgentRegistry.get_runner (external dependency boundary).
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from src.application.use_cases.thread_management import (
    CreateThreadUseCase,
    DeleteThreadUseCase,
    GetThreadUseCase,
    ListThreadsUseCase,
)
from src.domain.entities.agent_config_metadata import AgentConfigMetadata
from src.domain.exceptions import AgentNotFoundError, ThreadNotFoundError
from src.domain.ports.agent_config_repository import AgentConfigRepository
from src.domain.ports.agent_config_store import AgentConfigStore
from src.infrastructure.persistent_registry.adapter import PersistentAgentRegistry
from src.infrastructure.yaml_config.adapter import YamlAgentConfigLoader

VALID_YAML = (
    "name: test-agent\n"
    "model: test-model\n"
    'system_prompt: "Test."\n'
    "tools: []\n"
    "debug: false\n"
)


class TestCreateThreadUseCase:
    @pytest.fixture
    def mock_store(self):
        store = AsyncMock(spec=AgentConfigStore)
        store.get.return_value = VALID_YAML
        return store

    @pytest.fixture
    def mock_repository(self):
        repo = AsyncMock(spec=AgentConfigRepository)
        now = datetime.now(UTC)
        repo.list_all.return_value = [
            AgentConfigMetadata(
                name="test-agent",
                model="test-model",
                minio_path="test-agent.yaml",
                created_at=now,
                updated_at=now,
            )
        ]
        return repo

    @pytest.fixture
    def registry(self, mock_store, mock_repository, mock_mcp_tool_loader):
        return PersistentAgentRegistry(
            config_loader=YamlAgentConfigLoader(),
            config_store=mock_store,
            config_repository=mock_repository,
            mcp_tool_loader=mock_mcp_tool_loader,
        )

    async def test_create_thread(self, thread_repo, registry):
        use_case = CreateThreadUseCase(thread_repo, registry)
        thread = await use_case.execute("test-agent")

        assert thread.agent_name == "test-agent"
        assert thread.id is not None

    async def test_create_thread_unknown_agent_raises(self, thread_repo, registry, mock_store):
        from src.domain.exceptions import AgentNotFoundError as ANF

        mock_store.get.side_effect = ANF("not found")
        use_case = CreateThreadUseCase(thread_repo, registry)

        with pytest.raises(AgentNotFoundError):
            await use_case.execute("nonexistent-agent")


class TestGetThreadUseCase:
    async def test_get_thread(self, thread_repo):
        created = await thread_repo.create("test-agent")
        use_case = GetThreadUseCase(thread_repo)

        thread = await use_case.execute(created.id)

        assert thread.id == created.id

    async def test_get_nonexistent_thread_raises(self, thread_repo):
        use_case = GetThreadUseCase(thread_repo)

        with pytest.raises(ThreadNotFoundError):
            await use_case.execute("nonexistent-id")


class TestListThreadsUseCase:
    async def test_list_threads(self, thread_repo):
        await thread_repo.create("agent-1")
        await thread_repo.create("agent-2")
        use_case = ListThreadsUseCase(thread_repo)

        result = await use_case.execute()

        assert len(result) == 2


class TestDeleteThreadUseCase:
    async def test_delete_thread(self, thread_repo):
        created = await thread_repo.create("test-agent")
        use_case = DeleteThreadUseCase(thread_repo)

        await use_case.execute(created.id)

        with pytest.raises(ThreadNotFoundError):
            await thread_repo.get(created.id)
