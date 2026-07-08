import logging

from src.domain.ports.thread_repository import ThreadRepository

logger = logging.getLogger(__name__)


class DeleteThreadUseCase:
    def __init__(self, threads: ThreadRepository) -> None:
        self._threads = threads

    async def execute(self, thread_id: str) -> None:
        await self._threads.delete(thread_id)
