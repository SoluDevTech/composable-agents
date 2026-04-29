import logging
import time
from collections.abc import AsyncGenerator

from src.domain.entities.message import Message, MessageRole
from src.domain.entities.stream_event import StreamEvent, StreamEventType
from src.domain.ports.agent_registry import AgentRegistry
from src.domain.ports.thread_repository import ThreadRepository

logger = logging.getLogger("composable-agents")


class StreamMessageUseCase:
    """Envoie un message a l'agent et streame la reponse avec le Message final."""

    def __init__(self, registry: AgentRegistry, threads: ThreadRepository):
        self._registry = registry
        self._threads = threads

    async def execute(self, thread_id: str, message: str) -> AsyncGenerator[StreamEvent, None]:
        thread = await self._threads.get(thread_id)
        human_msg = Message(role=MessageRole.HUMAN, content=message)
        await self._threads.add_message(thread_id, human_msg)
        runner = await self._registry.get_runner(thread.agent_name)
        start = time.monotonic()
        logger.info("[thread=%s][agent=%s] Stream started", thread_id, thread.agent_name)
        chunk_count = 0
        final_message = None
        try:
            async for event in runner.stream_with_message(thread_id, message):
                if event.type in (StreamEventType.THINKING, StreamEventType.CONTENT):
                    chunk_count += 1
                    yield event
                elif event.type == StreamEventType.MESSAGE:
                    final_message = Message.model_validate_json(event.data)
                    yield event
        except Exception:
            logger.exception(
                "[thread=%s][agent=%s] Stream error after %d chunks", thread_id, thread.agent_name, chunk_count
            )
            raise
        elapsed = time.monotonic() - start
        if final_message is not None:
            try:
                await self._threads.add_message(thread_id, final_message)
            except Exception:
                logger.exception(
                    "[thread=%s][agent=%s] Failed to persist AI message after stream", thread_id, thread.agent_name
                )
            logger.info(
                "[thread=%s][agent=%s] Stream complete, %d chunks, elapsed=%.2fs, message=persisted",
                thread_id,
                thread.agent_name,
                chunk_count,
                elapsed,
            )
