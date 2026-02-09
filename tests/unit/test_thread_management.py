import pytest
from src.application.use_cases.thread_management import *
from src.domain.exceptions import AgentNotFoundError, ThreadNotFoundError
from src.infrastructure.memory_thread.adapter import InMemoryThreadRepository
from tests.doubles.fake_agent_registry import FakeAgentRegistry


class TestThreadUseCases:
    @pytest.mark.asyncio
    async def test_create_thread(self):
        threads = InMemoryThreadRepository()
        registry = FakeAgentRegistry()
        registry.register("test-agent")
        use_case = CreateThreadUseCase(threads, registry)
        thread = await use_case.execute("test-agent")
        assert thread.agent_name == "test-agent"
        assert thread.id is not None

    @pytest.mark.asyncio
    async def test_create_thread_unknown_agent_raises(self):
        threads = InMemoryThreadRepository()
        registry = FakeAgentRegistry()
        use_case = CreateThreadUseCase(threads, registry)
        with pytest.raises(AgentNotFoundError):
            await use_case.execute("nonexistent-agent")

    @pytest.mark.asyncio
    async def test_get_thread(self):
        threads = InMemoryThreadRepository()
        created = await threads.create("test-agent")
        use_case = GetThreadUseCase(threads)
        thread = await use_case.execute(created.id)
        assert thread.id == created.id

    @pytest.mark.asyncio
    async def test_list_threads(self):
        threads = InMemoryThreadRepository()
        await threads.create("agent-1")
        await threads.create("agent-2")
        use_case = ListThreadsUseCase(threads)
        result = await use_case.execute()
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_delete_thread(self):
        threads = InMemoryThreadRepository()
        created = await threads.create("test-agent")
        use_case = DeleteThreadUseCase(threads)
        await use_case.execute(created.id)
        with pytest.raises(ThreadNotFoundError):
            await threads.get(created.id)

    @pytest.mark.asyncio
    async def test_get_nonexistent_thread_raises(self):
        threads = InMemoryThreadRepository()
        use_case = GetThreadUseCase(threads)
        with pytest.raises(ThreadNotFoundError):
            await use_case.execute("nonexistent-id")
