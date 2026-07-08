import json
import logging
import time
from collections.abc import AsyncGenerator

from src.domain.entities.message import Message, MessageRole
from src.domain.entities.stream_event import StreamEvent, StreamEventType
from src.domain.errors.messages import ErrorMessage
from src.domain.errors.storage import StorageError
from src.domain.logging.messages import LogMessage
from src.domain.ports.agent_registry import AgentRegistry
from src.domain.ports.thread_repository import ThreadRepository

logger = logging.getLogger(__name__)


class StreamMessageUseCase:
    """Envoie un message a l'agent et streame la reponse avec le Message final."""

    def __init__(self, registry: AgentRegistry, threads: ThreadRepository) -> None:
        self._registry = registry
        self._threads = threads

    @staticmethod
    def _is_duplicate_human_message(messages: list, message: str) -> bool:
        """Detect duplicate HUMAN message submissions (crash/retry scenario).

        When a stream crashes before the AI response is persisted, the last DB message
        is HUMAN with status=None. On client retry, this check prevents storing a
        duplicate HUMAN message in the DB.

        NOTE: The graph invocation still proceeds (LangGraph will add the human message
        to its internal checkpoint state). This is intentional — the graph needs to be
        invoked to produce a response. The trade-off is that the LangGraph checkpoint
        may accumulate duplicate human messages, but the DB projection remains clean.
        """
        if not messages:
            return False
        last = messages[-1]
        return (
            last.role == MessageRole.HUMAN
            and last.content == message
            and last.status is None
        )

    async def execute(self, thread_id: str, message: str) -> AsyncGenerator[StreamEvent, None]:
        thread = await self._threads.get(thread_id)
        if not self._is_duplicate_human_message(thread.messages, message):
            human_msg = Message(role=MessageRole.HUMAN, content=message)
            await self._threads.add_message(thread_id, human_msg)
        else:
            logger.info(LogMessage.CHAT_SKIP_DUPLICATE_HUMAN, thread_id)
        runner = await self._registry.get_runner(thread.agent_name)
        start = time.monotonic()
        logger.info(LogMessage.CHAT_STREAM_STARTED, thread_id, thread.agent_name)
        chunk_count = 0
        final_message = None
        try:
            async for event in runner.stream_with_message(thread_id, message):
                if event.type in (StreamEventType.THINKING, StreamEventType.CONTENT):
                    chunk_count += 1
                    yield event
                elif event.type == StreamEventType.MESSAGE:
                    final_message = Message.model_validate_json(event.data)
                    if final_message and final_message.structured_response is not None:
                        event = StreamEvent(
                            type=StreamEventType.STRUCTURED,
                            data=json.dumps(final_message.structured_response)
                        )
                    yield event
        except Exception:
            logger.exception(
                LogMessage.CHAT_STREAM_ERROR_UC, thread_id, thread.agent_name, chunk_count
            )
            raise
        elapsed = time.monotonic() - start
        if final_message is not None:
            try:
                await self._threads.add_message(thread_id, final_message)
                logger.info(
                    LogMessage.CHAT_STREAM_COMPLETE_PERSISTED,
                    thread_id,
                    thread.agent_name,
                    chunk_count,
                    elapsed,
                )
            except Exception as exc:
                logger.exception(
                    LogMessage.CHAT_STREAM_PERSIST_FAILED, thread_id, thread.agent_name
                )
                raise StorageError(ErrorMessage.STORAGE_FAILED_PERSIST_STREAM.format(error=exc)) from exc
