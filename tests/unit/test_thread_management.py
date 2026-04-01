"""Tests for thread management use cases.

Uses real InMemoryThreadRepository (internal).
Uses AsyncMock for AgentRegistry.get_runner (external dependency boundary).
"""

import pytest

from src.application.use_cases.thread_management import (
    CreateThreadUseCase,
    DeleteThreadUseCase,
    GetThreadUseCase,
    ListThreadsUseCase,
)
from src.domain.exceptions import AgentNotFoundError, ThreadNotFoundError
from src.infrastructure.deepagent.registry import DeepAgentRegistry
from src.infrastructure.yaml_config.adapter import YamlAgentConfigLoader


class TestCreateThreadUseCase:
    @pytest.fixture
    def agents_dir(self, tmp_path):
        d = tmp_path / "agents"
        d.mkdir()
        (d / "test-agent.yaml").write_text("name: test-agent")
        return d

    @pytest.fixture
    def registry(self, agents_dir, mock_mcp_tool_loader):
        """Real DeepAgentRegistry with real YAML files."""
        return DeepAgentRegistry(
            agents_dir=agents_dir,
            config_loader=YamlAgentConfigLoader(),
            mcp_tool_loader=mock_mcp_tool_loader,
        )

    async def test_create_thread(self, thread_repo, registry):
        use_case = CreateThreadUseCase(thread_repo, registry)
        thread = await use_case.execute("test-agent")

        assert thread.agent_name == "test-agent"
        assert thread.id is not None

    async def test_create_thread_unknown_agent_raises(self, thread_repo, registry):
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
