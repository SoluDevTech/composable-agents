import logging

from src.domain.entities.thread import Thread
from src.domain.ports.thread_repository import ThreadRepository

logger = logging.getLogger(__name__)


class GetThreadUseCase:
    def __init__(self, threads: ThreadRepository) -> None:
        self._threads = threads

    async def execute(self, thread_id: str) -> Thread:
        return await self._threads.get(thread_id)
