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

router = APIRouter(prefix="/api/v1/threads", tags=["threads"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_thread(
    body: CreateThreadRequest,
    use_case: Annotated[CreateThreadUseCase, Depends(get_create_thread_use_case)],
) -> Thread:
    """Create a new conversation thread.

    Args:
        body: Request containing the agent name.
        use_case: Injected CreateThreadUseCase.

    Returns:
        The newly created Thread.
    """
    return await use_case.execute(body.agent_name)


@router.get("")
async def list_threads(
    use_case: Annotated[ListThreadsUseCase, Depends(get_list_threads_use_case)],
) -> list[Thread]:
    """List all conversation threads.

    Args:
        use_case: Injected ListThreadsUseCase.

    Returns:
        A list of all threads.
    """
    return await use_case.execute()


@router.get("/{thread_id}")
async def get_thread(
    thread_id: str,
    use_case: Annotated[GetThreadUseCase, Depends(get_get_thread_use_case)],
) -> Thread:
    """Get a specific thread by ID.

    Args:
        thread_id: The thread identifier.
        use_case: Injected GetThreadUseCase.

    Returns:
        The requested Thread.

    Raises:
        ThreadNotFoundError: If the thread does not exist.
    """
    return await use_case.execute(thread_id)


@router.delete("/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    thread_id: str,
    use_case: Annotated[DeleteThreadUseCase, Depends(get_delete_thread_use_case)],
) -> None:
    """Delete a thread by ID.

    Args:
        thread_id: The thread identifier.
        use_case: Injected DeleteThreadUseCase.

    Raises:
        ThreadNotFoundError: If the thread does not exist.
    """
    await use_case.execute(thread_id)


@router.get("/{thread_id}/messages")
async def list_messages(
    thread_id: str,
    use_case: Annotated[GetThreadUseCase, Depends(get_get_thread_use_case)],
) -> list:
    """List all messages in a thread.

    Args:
        thread_id: The thread identifier.
        use_case: Injected GetThreadUseCase.

    Returns:
        A list of messages in the thread.

    Raises:
        ThreadNotFoundError: If the thread does not exist.
    """
    thread = await use_case.execute(thread_id)
    return thread.messages
