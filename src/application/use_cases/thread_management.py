import logging

from src.domain.entities.thread import Thread
from src.domain.exceptions import AgentNotFoundError
from src.domain.ports.agent_registry import AgentRegistry
from src.domain.ports.thread_repository import ThreadRepository

logger = logging.getLogger("composable-agents")


class CreateThreadUseCase:
    def __init__(self, threads: ThreadRepository, registry: AgentRegistry):
        self._threads = threads
        self._registry = registry

    async def execute(self, agent_name: str) -> Thread:
        if agent_name not in await self._registry.list_agents():
            logger.error("Agent not found: %s", agent_name)
            raise AgentNotFoundError(f"Agent not found: {agent_name}")
        thread = await self._threads.create(agent_name)
        logger.info("Thread created: id=%s agent=%s", thread.id, agent_name)
        return thread


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
