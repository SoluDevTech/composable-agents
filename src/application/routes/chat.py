import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from src.application.requests.chat import ChatRequest
from src.application.use_cases.send_message import SendMessageUseCase
from src.application.use_cases.stream_message import StreamMessageUseCase
from src.application.use_cases.thread_management import GetThreadUseCase
from src.dependencies import (
    get_get_thread_use_case,
    get_send_message_use_case,
    get_stream_message_use_case,
)
from src.domain.entities.message import Message
from src.domain.entities.stream_event import StreamEventType

logger = logging.getLogger("composable-agents")

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


@router.post("/{thread_id}")
async def send_message(
    thread_id: str,
    body: ChatRequest,
    use_case: Annotated[SendMessageUseCase, Depends(get_send_message_use_case)],
) -> Message:
    logger.info("[thread=%s] POST /chat - message=%s", thread_id, "HITL" if body.message is None else body.message[:80])
    result = await use_case.execute(thread_id, body)
    logger.info("[thread=%s] Response status=%s content_len=%d", thread_id, result.status, len(result.content or ""))
    return result


@router.post("/{thread_id}/stream")
async def stream_message(
    thread_id: str,
    body: ChatRequest,
    use_case: Annotated[StreamMessageUseCase, Depends(get_stream_message_use_case)],
    get_thread: Annotated[GetThreadUseCase, Depends(get_get_thread_use_case)],
) -> EventSourceResponse:
    logger.info("[thread=%s] POST /chat/stream - message=%s", thread_id, (body.message or "")[:80])
    await get_thread.execute(thread_id)

    async def event_generator():
        chunk_count = 0
        try:
            async for event in use_case.execute(thread_id, body.message):
                if event.type in (StreamEventType.THINKING, StreamEventType.CONTENT):
                    chunk_count += 1
                yield {"data": event.model_dump_json()}
            yield {"data": "[DONE]"}
            logger.info("[thread=%s] Stream complete, %d chunks", thread_id, chunk_count)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[thread=%s] Stream error after %d chunks", thread_id, chunk_count)
            yield {"event": "error", "data": "stream_error"}

    return EventSourceResponse(event_generator(), sep="\r\n", ping=15)
