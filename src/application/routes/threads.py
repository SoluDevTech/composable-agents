import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status

from src.application.requests.chat import CreateThreadRequest
from src.application.use_cases.thread_management import (
    CreateThreadUseCase,
    DeleteThreadUseCase,
    GetThreadUseCase,
    ListThreadsUseCase,
)
from src.dependencies import (
    get_create_thread_use_case,
    get_delete_thread_use_case,
    get_get_thread_use_case,
    get_list_threads_use_case,
)
from src.domain.entities.thread import Thread

logger = logging.getLogger("composable-agents")

router = APIRouter(prefix="/api/v1/threads", tags=["threads"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_thread(
    body: CreateThreadRequest,
    use_case: Annotated[CreateThreadUseCase, Depends(get_create_thread_use_case)],
) -> Thread:
    logger.info("Creating thread for agent=%s", body.agent_name)
    thread = await use_case.execute(body.agent_name)
    logger.info("Thread created: id=%s agent=%s", thread.id, thread.agent_name)
    return thread


@router.get("")
async def list_threads(
    use_case: Annotated[ListThreadsUseCase, Depends(get_list_threads_use_case)],
) -> list[Thread]:
    threads = await use_case.execute()
    logger.debug("Listed %d threads", len(threads))
    return threads


@router.get("/{thread_id}")
async def get_thread(
    thread_id: str,
    use_case: Annotated[GetThreadUseCase, Depends(get_get_thread_use_case)],
) -> Thread:
    logger.debug("Getting thread=%s", thread_id)
    return await use_case.execute(thread_id)


@router.delete("/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    thread_id: str,
    use_case: Annotated[DeleteThreadUseCase, Depends(get_delete_thread_use_case)],
) -> None:
    logger.info("Deleting thread=%s", thread_id)
    await use_case.execute(thread_id)


@router.get("/{thread_id}/messages")
async def list_messages(
    thread_id: str,
    use_case: Annotated[GetThreadUseCase, Depends(get_get_thread_use_case)],
) -> list:
    thread = await use_case.execute(thread_id)
    logger.debug("[thread=%s] Listed %d messages", thread_id, len(thread.messages))
    return thread.messages
