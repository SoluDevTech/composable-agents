"""StreamMessageUseCase — stream all TraceEvents of a turn and persist each one.

Ticket 3 rewrite: the use case depends on TraceEventRepository + the new runner
API ``stream(thread_id, message, turn_id) -> AsyncIterator[TraceEvent]``. Each
emitted event is persisted via ``trace_repo.add`` before being yielded to the
HTTP/WebSocket layer.
"""

import logging
import uuid
from collections.abc import AsyncGenerator

from src.domain.entities.trace_event import TraceEvent
from src.domain.errors.messages import ErrorMessage
from src.domain.errors.storage import StorageError
from src.domain.logging.messages import LogMessage
from src.domain.ports.agent_registry import AgentRegistry
from src.domain.ports.thread_repository import ThreadRepository
from src.domain.ports.trace_event_repository import TraceEventRepository

logger = logging.getLogger(__name__)


class StreamMessageUseCase:
    """Stream all TraceEvents of a turn and persist each one.

    Each event emitted by the runner is persisted via ``trace_repo.add`` before
    being yielded, so the trace is durably stored even if the client disconnects
    mid-stream.
    """

    def __init__(self, registry: AgentRegistry, threads: ThreadRepository, trace_repo: TraceEventRepository) -> None:
        self._registry = registry
        self._threads = threads
        self._trace_repo = trace_repo

    async def execute(self, thread_id: str, message: str) -> AsyncGenerator[TraceEvent, None]:
        """Execute the use case.

        Args:
            thread_id: Conversation thread identifier.
            message: Human message text.

        Yields:
            Each :class:`TraceEvent` emitted by the runner (HUMAN_MESSAGE,
            intermediates, then AI_MESSAGE), in turn order.

        Raises:
            ThreadNotFoundError: If the thread does not exist.
            AgentError: On runner failure.
            StorageError: If persisting an event fails.
        """
        thread = await self._threads.get(thread_id)
        runner = await self._registry.get_runner(thread.agent_name)
        turn_id = str(uuid.uuid4())
        logger.info(LogMessage.CHAT_STREAM_STARTED, thread_id, thread.agent_name)
        chunk_count = 0
        try:
            async for event in runner.stream(thread_id, message, turn_id):
                try:
                    await self._trace_repo.add(thread_id, event)
                except Exception as exc:
                    logger.exception(LogMessage.CHAT_STREAM_PERSIST_FAILED, thread_id, thread.agent_name)
                    raise StorageError(ErrorMessage.STORAGE_FAILED_PERSIST_STREAM.format(error=exc)) from exc
                chunk_count += 1
                yield event
        except Exception:
            logger.exception(LogMessage.CHAT_STREAM_ERROR_UC, thread_id, thread.agent_name, chunk_count)
            raise
