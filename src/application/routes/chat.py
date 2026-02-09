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

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


@router.post("/{thread_id}")
async def send_message(
    thread_id: str,
    body: ChatRequest,
    use_case: Annotated[SendMessageUseCase, Depends(get_send_message_use_case)],
) -> Message:
    """Send a message or HITL decision to the agent and get the response.

    Args:
        thread_id: The conversation thread identifier.
        body: Request containing either a user message or an HITL decision.
        use_case: Injected SendMessageUseCase.

    Returns:
        The agent's response Message.

    Raises:
        ThreadNotFoundError: If the thread does not exist.
    """
    return await use_case.execute(thread_id, body)


@router.post("/{thread_id}/stream")
async def stream_message(
    thread_id: str,
    body: ChatRequest,
    use_case: Annotated[StreamMessageUseCase, Depends(get_stream_message_use_case)],
    get_thread: Annotated[GetThreadUseCase, Depends(get_get_thread_use_case)],
) -> EventSourceResponse:
    """Send a message and stream the response via SSE.

    The thread is validated before the stream starts so that a missing
    thread is reported as a 404 instead of failing silently inside the
    SSE generator.

    Args:
        thread_id: The conversation thread identifier.
        body: Request containing the user message.
        use_case: Injected StreamMessageUseCase.
        get_thread: Injected GetThreadUseCase used for pre-validation.

    Returns:
        An EventSourceResponse streaming chunks.

    Raises:
        ThreadNotFoundError: If the thread does not exist.
    """
    # Pre-validate the thread exists before starting the SSE stream.
    await get_thread.execute(thread_id)

    async def event_generator():
        async for chunk in use_case.execute(thread_id, body.message):
            yield {"data": chunk}

    return EventSourceResponse(event_generator())
