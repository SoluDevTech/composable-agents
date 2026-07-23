"""PostgreSQL adapter for the ThreadRepository port.

Each method opens its own :class:`AsyncSession` (session-per-method). The
``add_message`` method has been removed — message persistence now goes through
:class:`~src.infrastructure.postgres_trace.adapter.PostgresTraceEventRepository`.
"""

import logging
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import selectinload

from src.domain.entities.thread import Thread
from src.domain.entities.trace_event import TraceEvent, TraceEventType
from src.domain.errors.messages import ErrorMessage
from src.domain.errors.storage import StorageError
from src.domain.errors.thread import ThreadNotFoundError
from src.domain.ports.thread_repository import ThreadRepository
from src.infrastructure.database.models.thread import ThreadModel

logger = logging.getLogger(__name__)


def _model_to_thread(thread_model: ThreadModel) -> Thread:
    """Reconstruct a domain Thread from ORM ThreadModel with its TraceEventModels.

    Trace events are sorted by timestamp (oldest first). The database
    relationship already has ``order_by``, but sorting here is a defensive
    measure.

    Args:
        thread_model: The ORM thread model with loaded trace_events relationship.

    Returns:
        A domain Thread entity with all trace events.
    """
    events_sorted = sorted(thread_model.trace_events, key=lambda m: m.timestamp)
    trace_events = [
        TraceEvent(
            id=m.id,
            thread_id=m.thread_id,
            turn_id=m.turn_id,
            type=TraceEventType(m.type),
            source=m.source,
            name=m.name,
            content=m.content,
            metadata=m.event_metadata,
            timestamp=m.timestamp,
            sequence=m.sequence,
        )
        for m in events_sorted
    ]
    return Thread(
        id=thread_model.id,
        agent_name=thread_model.agent_name,
        trace_events=trace_events,
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
                # New thread has no trace_events — construct directly to avoid lazy='raise'
                return Thread(
                    id=model.id,
                    agent_name=model.agent_name,
                    trace_events=[],
                    created_at=model.created_at,
                    updated_at=model.updated_at,
                )
            except SQLAlchemyError as e:
                raise StorageError(ErrorMessage.THREAD_FAILED_CREATE.format(error=e)) from e

    async def get(self, thread_id: str) -> Thread:
        """Retrieve a thread by its ID.

        Args:
            thread_id: The unique thread identifier.

        Returns:
            The domain Thread with all trace events.

        Raises:
            ThreadNotFoundError: If no thread exists with this ID.
            StorageError: If the database operation fails.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                model = await session.get(ThreadModel, thread_id, options=[selectinload(ThreadModel.trace_events)])
                if model is None:
                    raise ThreadNotFoundError(ErrorMessage.THREAD_NOT_FOUND.format(thread_id=thread_id))
                return _model_to_thread(model)
            except ThreadNotFoundError:
                raise
            except SQLAlchemyError as e:
                raise StorageError(ErrorMessage.THREAD_FAILED_GET.format(thread_id=thread_id, error=e)) from e

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
                    .options(selectinload(ThreadModel.trace_events))
                    .order_by(ThreadModel.created_at.desc())
                )
                models = result.scalars().all()
                return [_model_to_thread(model) for model in models]
            except SQLAlchemyError as e:
                raise StorageError(ErrorMessage.THREAD_FAILED_LIST.format(error=e)) from e

    async def delete(self, thread_id: str) -> None:
        """Delete a thread and all its trace events.

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
                    raise ThreadNotFoundError(ErrorMessage.THREAD_NOT_FOUND.format(thread_id=thread_id))
                await session.delete(model)
                await session.commit()
            except ThreadNotFoundError:
                raise
            except SQLAlchemyError as e:
                raise StorageError(ErrorMessage.THREAD_FAILED_DELETE.format(thread_id=thread_id, error=e)) from e
