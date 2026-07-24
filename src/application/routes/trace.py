"""Trace HTTP route: GET /api/v1/threads/{id}/trace.

Returns the flat list of TraceEvents for a thread (ordered by timestamp).
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from src.application.use_cases.get_thread import GetThreadUseCase
from src.dependencies import get_get_thread_use_case, get_trace_event_repository
from src.domain.entities.trace_event import TraceEvent
from src.domain.logging.messages import LogMessage
from src.domain.ports.trace_event_repository import TraceEventRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/threads", tags=["trace"])


@router.get("/{thread_id}/trace")
async def list_trace(
    thread_id: str,
    repo: Annotated[TraceEventRepository, Depends(get_trace_event_repository)],
    use_case: Annotated[GetThreadUseCase, Depends(get_get_thread_use_case)],
) -> dict:
    """Return the flat list of all TraceEvents for a thread.

    Args:
        thread_id: Conversation thread identifier.
        repo: TraceEventRepository wired at startup.
        use_case: GetThreadUseCase used to validate the thread exists.

    Returns:
        ``{"events": [TraceEvent, ...]}`` ordered by timestamp.
    """
    logger.info(LogMessage.THREAD_GETTING, thread_id)
    # Validate the thread exists first to align with /history and /messages
    # (which raise 404 for unknown threads).
    await use_case.execute(thread_id)
    events: list[TraceEvent] = await repo.list_by_thread(thread_id)
    return {"events": events}
