"""In-memory thread repository for testing use cases.

This is a test-only implementation that provides a simple in-memory store
for use case tests that need a real (non-mocked) ThreadRepository.
"""

import logging
from datetime import UTC, datetime

from src.domain.entities.message import Message
from src.domain.entities.thread import Thread
from src.domain.exceptions import ThreadNotFoundError
from src.domain.ports.thread_repository import ThreadRepository

logger = logging.getLogger("composable-agents")


class InMemoryThreadRepository(ThreadRepository):
    """In-memory thread storage for testing."""

    def __init__(self):
        self._threads: dict[str, Thread] = {}

    async def create(self, agent_name: str) -> Thread:
        thread = Thread(agent_name=agent_name)
        self._threads[thread.id] = thread
        return thread

    async def get(self, thread_id: str) -> Thread:
        if thread_id not in self._threads:
            raise ThreadNotFoundError(f"Thread not found: {thread_id}")
        return self._threads[thread_id]

    async def list_all(self) -> list[Thread]:
        return list(self._threads.values())

    async def delete(self, thread_id: str) -> None:
        if thread_id not in self._threads:
            raise ThreadNotFoundError(f"Thread not found: {thread_id}")
        del self._threads[thread_id]

    async def add_message(self, thread_id: str, message: Message) -> Thread:
        thread = await self.get(thread_id)
        thread.messages.append(message)
        thread.updated_at = datetime.now(UTC)
        return thread
