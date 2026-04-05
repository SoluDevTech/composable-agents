import logging
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import selectinload

from src.domain.entities.message import Message, MessageRole, MessageStatus
from src.domain.entities.thread import Thread
from src.domain.exceptions import StorageError, ThreadNotFoundError
from src.domain.ports.thread_repository import ThreadRepository
from src.infrastructure.database.models.thread import MessageModel, ThreadModel

logger = logging.getLogger("composable-agents")


def _model_to_thread(thread_model: ThreadModel) -> Thread:
    """Reconstruct a domain Thread from ORM ThreadModel with its MessageModels.

    Messages are sorted by timestamp (oldest first).
    The database relationship has order_by, but sort is kept as a defensive measure.

    Args:
        thread_model: The ORM thread model with loaded messages relationship.

    Returns:
        A domain Thread entity with all messages.
    """
    messages_sorted = sorted(thread_model.messages, key=lambda m: m.timestamp)
    messages = [
        Message(
            role=MessageRole(msg.role),
            content=msg.content,
            timestamp=msg.timestamp,
            tool_calls=msg.tool_calls,
            status=MessageStatus(msg.status) if msg.status else None,
            structured_response=msg.structured_response,
        )
        for msg in messages_sorted
    ]
    return Thread(
        id=thread_model.id,
        agent_name=thread_model.agent_name,
        messages=messages,
        created_at=thread_model.created_at,
        updated_at=thread_model.updated_at,
    )


class PostgresThreadRepository(ThreadRepository):
    """Adapter that persists conversation threads in PostgreSQL via SQLAlchemy async.

    Each method creates its own AsyncSession from the engine, ensuring thread-safety
    and proper session lifecycle for concurrent operations.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def create(self, agent_name: str) -> Thread:
        """Create a new conversation thread.

        Args:
            agent_name: Name of the agent owning this thread.

        Returns:
            The newly created Thread.

        Raises:
            StorageError: If the database operation fails.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                now = datetime.now(UTC)
                model = ThreadModel(
                    id=str(uuid4()),
                    agent_name=agent_name,
                    created_at=now,
                    updated_at=now,
                )
                session.add(model)
                await session.commit()
                # New thread has no messages — construct directly to avoid lazy='raise'
                return Thread(
                    id=model.id,
                    agent_name=model.agent_name,
                    messages=[],
                    created_at=model.created_at,
                    updated_at=model.updated_at,
                )
            except SQLAlchemyError as e:
                raise StorageError(f"Failed to create thread: {e}") from e

    async def get(self, thread_id: str) -> Thread:
        """Retrieve a thread by its ID.

        Args:
            thread_id: The unique thread identifier.

        Returns:
            The domain Thread with all messages.

        Raises:
            ThreadNotFoundError: If no thread exists with this ID.
            StorageError: If the database operation fails.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                model = await session.get(
                    ThreadModel, thread_id, options=[selectinload(ThreadModel.messages)]
                )
                if model is None:
                    raise ThreadNotFoundError(f"Thread not found: {thread_id}")
                return _model_to_thread(model)
            except ThreadNotFoundError:
                raise
            except SQLAlchemyError as e:
                raise StorageError(f"Failed to get thread {thread_id}: {e}") from e

    async def list_all(self) -> list[Thread]:
        """List all conversation threads.

        Returns:
            A list of all Thread entities.

        Raises:
            StorageError: If the database operation fails.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                result = await session.execute(
                    select(ThreadModel)
                    .options(selectinload(ThreadModel.messages))
                    .order_by(ThreadModel.created_at.desc())
                )
                models = result.scalars().all()
                return [_model_to_thread(model) for model in models]
            except SQLAlchemyError as e:
                raise StorageError(f"Failed to list threads: {e}") from e

    async def delete(self, thread_id: str) -> None:
        """Delete a thread and all its messages.

        Args:
            thread_id: The unique thread identifier.

        Raises:
            ThreadNotFoundError: If no thread exists with this ID.
            StorageError: If the database operation fails.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                model = await session.get(ThreadModel, thread_id)
                if model is None:
                    raise ThreadNotFoundError(f"Thread not found: {thread_id}")
                await session.delete(model)
                await session.commit()
            except ThreadNotFoundError:
                raise
            except SQLAlchemyError as e:
                raise StorageError(f"Failed to delete thread {thread_id}: {e}") from e

    async def add_message(self, thread_id: str, message: Message) -> Thread:
        """Add a message to an existing thread.

        Args:
            thread_id: The unique thread identifier.
            message: The domain Message to add.

        Returns:
            The updated Thread with the new message included.

        Raises:
            ThreadNotFoundError: If no thread exists with this ID.
            StorageError: If the database operation fails.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                thread_model = await session.get(ThreadModel, thread_id)
                if thread_model is None:
                    raise ThreadNotFoundError(f"Thread not found: {thread_id}")

                msg_model = MessageModel(
                    id=str(uuid4()),
                    thread_id=thread_id,
                    role=message.role.value,
                    content=message.content,
                    timestamp=message.timestamp,
                    tool_calls=message.tool_calls,
                    status=message.status.value if message.status else None,
                    structured_response=message.structured_response,
                )
                session.add(msg_model)
                thread_model.updated_at = datetime.now(UTC)
                await session.commit()
                # session.get() with an expired identity-map object does NOT re-apply
                # selectinload options — use execute(select(...)) to force a real DB query.
                result = await session.execute(
                    select(ThreadModel)
                    .where(ThreadModel.id == thread_id)
                    .options(selectinload(ThreadModel.messages))
                    .execution_options(populate_existing=True)
                )
                updated_model = result.scalar_one()
                return _model_to_thread(updated_model)
            except ThreadNotFoundError:
                raise
            except SQLAlchemyError as e:
                raise StorageError(f"Failed to add message to thread {thread_id}: {e}") from e
