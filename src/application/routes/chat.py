"""Chat HTTP routes: POST /chat/{id} and POST /chat/{id}/stream.

Emits TraceEvent records (not the legacy StreamEvent). On stream error, the
generator emits a plain JSON error payload ``{"type": "error", "data": "..."}``
that is NOT a TraceEvent (TraceEventType has no ERROR variant) — this matches
the previous SSE contract for errors; the frontend already handles it.
"""

import asyncio
import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from src.application.requests.chat import ChatRequest
from src.application.use_cases.get_thread import GetThreadUseCase
from src.application.use_cases.send_message import SendMessageUseCase
from src.application.use_cases.stream_message import StreamMessageUseCase
from src.dependencies import (
    get_get_thread_use_case,
    get_send_message_use_case,
    get_stream_message_use_case,
)
from src.domain.entities.message import Message
from src.domain.logging.messages import LogMessage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


@router.post("/{thread_id}")
async def send_message(
    thread_id: str,
    body: ChatRequest,
    use_case: Annotated[SendMessageUseCase, Depends(get_send_message_use_case)],
) -> Message:
    """Send a human message or an HITL decision and return the final AI Message.

    Args:
        thread_id: Conversation thread identifier.
        body: Chat request (message XOR HITL fields).

    Returns:
        The final AI Message.
    """
    logger.info(LogMessage.CHAT_RECEIVE, thread_id, "HITL" if body.message is None else body.message[:80])
    result = await use_case.execute(
        thread_id,
        message=body.message,
        action=body.action,
        tool_call_id=body.tool_call_id,
        reason=body.reason,
        edits=body.edits,
        decisions=body.decisions,
    )
    logger.info(LogMessage.CHAT_RESPONSE, thread_id, result.status, len(result.content or ""))
    return result


@router.post("/{thread_id}/stream")
async def stream_message(
    thread_id: str,
    body: ChatRequest,
    use_case: Annotated[StreamMessageUseCase, Depends(get_stream_message_use_case)],
    get_thread: Annotated[GetThreadUseCase, Depends(get_get_thread_use_case)],
) -> EventSourceResponse:
    """Stream all TraceEvents of a turn as SSE, then a ``[DONE]`` terminator.

    Each ``data:`` line carries a JSON-serialized TraceEvent. On error, a
    plain JSON error payload ``{"type": "error", "data": "..."}`` is emitted
    (this is NOT a TraceEvent — :class:`TraceEventType` has no ERROR variant),
    matching the previous SSE contract so the frontend keeps working.

    Args:
        thread_id: Conversation thread identifier.
        body: Chat request (must contain ``message``).
        get_thread: GetThreadUseCase used to validate the thread exists.

    Returns:
        An ``EventSourceResponse`` streaming TraceEvents.
    """
    logger.info(LogMessage.CHAT_STREAM_RECEIVE, thread_id, (body.message or "")[:80])
    await get_thread.execute(thread_id)

    async def event_generator():
        event_count = 0
        try:
            async for event in use_case.execute(thread_id, body.message or ""):
                event_count += 1
                yield {"data": event.model_dump_json()}
            yield {"data": "[DONE]"}
            logger.info(LogMessage.CHAT_STREAM_COMPLETE, thread_id, event_count)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception(LogMessage.CHAT_STREAM_ERROR, thread_id, event_count)
            yield {"data": json.dumps({"type": "error", "data": str(exc)})}

    return EventSourceResponse(event_generator(), sep="\r\n", ping=15)
