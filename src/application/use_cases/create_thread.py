import logging

from src.domain.entities.thread import Thread
from src.domain.errors.agent import AgentNotFoundError
from src.domain.errors.messages import ErrorMessage
from src.domain.logging.messages import LogMessage
from src.domain.ports.agent_registry import AgentRegistry
from src.domain.ports.thread_repository import ThreadRepository

logger = logging.getLogger(__name__)


class CreateThreadUseCase:
    def __init__(self, threads: ThreadRepository, registry: AgentRegistry) -> None:
        self._threads = threads
        self._registry = registry

    async def execute(self, agent_name: str) -> Thread:
        if agent_name not in await self._registry.list_agents():
            raise AgentNotFoundError(ErrorMessage.AGENT_NOT_FOUND.format(name=agent_name))
        thread = await self._threads.create(agent_name)
        logger.info(LogMessage.THREAD_CREATED, thread.id, agent_name)
        return thread
