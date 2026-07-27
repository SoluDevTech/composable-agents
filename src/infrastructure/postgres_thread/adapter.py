"""PostgreSQL adapter for the ThreadRepository port.

Each method opens its own :class:`AsyncSession` (session-per-method). The
``add_message`` method has been removed — message persistence now goes through
:class:`~src.infrastructure.postgres_trace.adapter.PostgresTraceEventRepository`.

Per-user isolation (RLS plumbing):

* The repository reads the ``current_user_id`` contextvar via
  :meth:`_current_user_id`.
* On **writes** (``create``) the row's ``user_id`` is set to the contextvar
  value (or ``""`` when unset, preserving existing behaviour).
* On **reads** (``get`` / ``list_all``) and **delete** a ``WHERE user_id ==
  <contextvar>`` filter is added when the contextvar is set. When the
  contextvar is ``None`` (no auth context, pre-auth-core tests) no filter is
  applied so existing behaviour is preserved.
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
from src.infrastructure.database.rls_context import current_user_id

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
            user_id=m.user_id,
        )
        for m in events_sorted
    ]
    return Thread(
        id=thread_model.id,
        agent_name=thread_model.agent_name,
        trace_events=trace_events,
        created_at=thread_model.created_at,
        updated_at=thread_model.updated_at,
        user_id=thread_model.user_id,
    )


class PostgresThreadRepository(ThreadRepository):
    """Adapter that persists conversation threads in PostgreSQL via SQLAlchemy async.

    Each method creates its own AsyncSession from the engine, ensuring thread-safety
    and proper session lifecycle for concurrent operations.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    @staticmethod
    def _current_user_id() -> str | None:
        """Return the ``current_user_id`` contextvar value or ``None``."""
        return current_user_id.get()

    async def create(self, agent_name: str) -> Thread:
        """Create a new conversation thread.

        The row's ``user_id`` is set from the ``current_user_id`` contextvar
        (or ``""`` when the contextvar is unset, preserving existing
        behaviour).

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
                uid = self._current_user_id() or ""
                model = ThreadModel(
                    id=str(uuid4()),
                    agent_name=agent_name,
                    created_at=now,
                    updated_at=now,
                    user_id=uid,
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
                    user_id=model.user_id,
                )
            except SQLAlchemyError as e:
                raise StorageError(ErrorMessage.THREAD_FAILED_CREATE.format(error=e)) from e

    async def get(self, thread_id: str) -> Thread:
        """Retrieve a thread by its ID.

        When ``current_user_id`` is set, a ``WHERE user_id == <ctx>`` filter
        is applied so a thread owned by another user appears as not found.

        Args:
            thread_id: The unique thread identifier.

        Returns:
            The domain Thread with all trace events.

        Raises:
            ThreadNotFoundError: If no thread exists with this ID (or it is
                owned by another user when the contextvar is set).
            StorageError: If the database operation fails.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                uid = self._current_user_id()
                if uid is None:
                    model = await session.get(ThreadModel, thread_id, options=[selectinload(ThreadModel.trace_events)])
                else:
                    stmt = (
                        select(ThreadModel)
                        .options(selectinload(ThreadModel.trace_events))
                        .where(ThreadModel.id == thread_id, ThreadModel.user_id == uid)
                    )
                    model = (await session.execute(stmt)).scalar_one_or_none()
                if model is None:
                    raise ThreadNotFoundError(ErrorMessage.THREAD_NOT_FOUND.format(thread_id=thread_id))
                return _model_to_thread(model)
            except ThreadNotFoundError:
                raise
            except SQLAlchemyError as e:
                raise StorageError(ErrorMessage.THREAD_FAILED_GET.format(thread_id=thread_id, error=e)) from e

    async def list_all(self) -> list[Thread]:
        """List all conversation threads visible to the current user.

        When ``current_user_id`` is set, only threads with
        ``user_id == <ctx>`` are returned. When the contextvar is ``None`` no
        filter is applied (existing behaviour).

        Returns:
            A list of all visible Thread entities.

        Raises:
            StorageError: If the database operation fails.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                uid = self._current_user_id()
                stmt = (
                    select(ThreadModel)
                    .options(selectinload(ThreadModel.trace_events))
                    .order_by(ThreadModel.created_at.desc())
                )
                if uid is not None:
                    stmt = stmt.where(ThreadModel.user_id == uid)
                result = await session.execute(stmt)
                models = result.scalars().all()
                return [_model_to_thread(model) for model in models]
            except SQLAlchemyError as e:
                raise StorageError(ErrorMessage.THREAD_FAILED_LIST.format(error=e)) from e

    async def delete(self, thread_id: str) -> None:
        """Delete a thread and all its trace events.

        When ``current_user_id`` is set, only a thread owned by the current
        user can be deleted (otherwise :class:`ThreadNotFoundError` is raised).

        Args:
            thread_id: The unique thread identifier.

        Raises:
            ThreadNotFoundError: If no thread exists with this ID (or it is
                owned by another user when the contextvar is set).
            StorageError: If the database operation fails.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                uid = self._current_user_id()
                if uid is None:
                    model = await session.get(ThreadModel, thread_id)
                else:
                    stmt = select(ThreadModel).where(ThreadModel.id == thread_id, ThreadModel.user_id == uid)
                    model = (await session.execute(stmt)).scalar_one_or_none()
                if model is None:
                    raise ThreadNotFoundError(ErrorMessage.THREAD_NOT_FOUND.format(thread_id=thread_id))
                await session.delete(model)
                await session.commit()
            except ThreadNotFoundError:
                raise
            except SQLAlchemyError as e:
                raise StorageError(ErrorMessage.THREAD_FAILED_DELETE.format(thread_id=thread_id, error=e)) from e
