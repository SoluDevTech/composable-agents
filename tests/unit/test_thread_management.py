"""Tests for thread management use cases.

Uses real InMemoryThreadRepository (internal).
Uses AsyncMock for AgentRegistry (external dependency boundary).
"""

from unittest.mock import AsyncMock

import pytest

from src.application.use_cases.thread_management import (
    CreateThreadUseCase,
    DeleteThreadUseCase,
    GetThreadUseCase,
    ListThreadsUseCase,
)
from src.domain.exceptions import AgentNotFoundError, ThreadNotFoundError
from src.domain.ports.agent_registry import AgentRegistry


class TestCreateThreadUseCase:
    @pytest.fixture
    def registry(self):
        """AsyncMock spec'd to AgentRegistry port."""
        mock = AsyncMock(spec=AgentRegistry)
        mock.list_agents.return_value = ["test-agent"]
        return mock

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
