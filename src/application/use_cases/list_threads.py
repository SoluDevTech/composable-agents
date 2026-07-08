import logging

from src.domain.entities.thread import Thread
from src.domain.ports.thread_repository import ThreadRepository

logger = logging.getLogger(__name__)


class ListThreadsUseCase:
    def __init__(self, threads: ThreadRepository) -> None:
        self._threads = threads

    async def execute(self) -> list[Thread]:
        return await self._threads.list_all()
