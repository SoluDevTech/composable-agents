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
from src.domain.entities.stream_event import StreamEvent, StreamEventType
from src.domain.logging.messages import LogMessage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


@router.post("/{thread_id}")
async def send_message(
    thread_id: str,
    body: ChatRequest,
    use_case: Annotated[SendMessageUseCase, Depends(get_send_message_use_case)],
) -> Message:
    logger.info(LogMessage.CHAT_RECEIVE, thread_id, "HITL" if body.message is None else body.message[:80])
    result = await use_case.execute(thread_id, body)
    logger.info(LogMessage.CHAT_RESPONSE, thread_id, result.status, len(result.content or ""))
    return result


@router.post("/{thread_id}/stream")
async def stream_message(
    thread_id: str,
    body: ChatRequest,
    use_case: Annotated[StreamMessageUseCase, Depends(get_stream_message_use_case)],
    get_thread: Annotated[GetThreadUseCase, Depends(get_get_thread_use_case)],
) -> EventSourceResponse:
    logger.info(LogMessage.CHAT_STREAM_RECEIVE, thread_id, (body.message or "")[:80])
    await get_thread.execute(thread_id)

    async def event_generator():
        chunk_count = 0
        try:
            async for event in use_case.execute(thread_id, body.message):
                if event.type in (StreamEventType.THINKING, StreamEventType.CONTENT):
                    chunk_count += 1
                yield {"data": event.model_dump_json()}
            yield {"data": "[DONE]"}
            logger.info(LogMessage.CHAT_STREAM_COMPLETE, thread_id, chunk_count)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception(LogMessage.CHAT_STREAM_ERROR, thread_id, chunk_count)
            error_event = StreamEvent(type=StreamEventType.ERROR, data=str(exc))
            yield {"data": error_event.model_dump_json()}

    return EventSourceResponse(event_generator(), sep="\r\n", ping=15)
