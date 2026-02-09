from src.domain.exceptions import AgentNotFoundError
from src.domain.ports.agent_registry import AgentRegistry
from src.domain.ports.thread_repository import ThreadRepository
from src.domain.entities.thread import Thread


class CreateThreadUseCase:
    def __init__(self, threads: ThreadRepository, registry: AgentRegistry):
        self._threads = threads
        self._registry = registry

    async def execute(self, agent_name: str) -> Thread:
        if agent_name not in self._registry.list_agents():
            raise AgentNotFoundError(f"Agent introuvable: {agent_name}")
        return await self._threads.create(agent_name)


class GetThreadUseCase:
    def __init__(self, threads: ThreadRepository):
        self._threads = threads

    async def execute(self, thread_id: str) -> Thread:
        return await self._threads.get(thread_id)


class ListThreadsUseCase:
    def __init__(self, threads: ThreadRepository):
        self._threads = threads

    async def execute(self) -> list[Thread]:
        return await self._threads.list_all()


class DeleteThreadUseCase:
    def __init__(self, threads: ThreadRepository):
        self._threads = threads

    async def execute(self, thread_id: str) -> None:
        await self._threads.delete(thread_id)
