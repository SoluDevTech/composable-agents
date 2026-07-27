"""PostgreSQL adapter for the TraceEventRepository port.

Each method opens its own :class:`AsyncSession` (session-per-method) to ensure
thread-safety and proper session lifecycle under concurrent FastAPI requests.

Per-user isolation (RLS plumbing): the repository reads the
``current_user_id`` contextvar and filters the parent thread lookup by
``user_id`` so a user can only add/list events on threads they own. The
``user_id`` is denormalized onto each ``trace_events`` row on insert so list
queries can filter without a JOIN. When the contextvar is ``None`` (no auth
context) no filter is applied so existing behaviour is preserved.
"""

import logging

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.domain.entities.trace_event import TraceEvent, TraceEventType
from src.domain.errors.messages import ErrorMessage
from src.domain.errors.storage import StorageError
from src.domain.errors.thread import ThreadNotFoundError
from src.domain.ports.trace_event_repository import TraceEventRepository
from src.infrastructure.database.models.thread import ThreadModel
from src.infrastructure.database.models.trace_event import TraceEventModel
from src.infrastructure.database.rls_context import current_user_id

logger = logging.getLogger(__name__)


def _model_to_event(model: TraceEventModel) -> TraceEvent:
    """Reconstruct a domain TraceEvent from its ORM model."""
    return TraceEvent(
        id=model.id,
        thread_id=model.thread_id,
        turn_id=model.turn_id,
        type=TraceEventType(model.type),
        source=model.source,
        name=model.name,
        content=model.content,
        metadata=model.event_metadata,
        timestamp=model.timestamp,
        sequence=model.sequence,
        user_id=model.user_id,
    )


class PostgresTraceEventRepository(TraceEventRepository):
    """Adapter that persists trace events in PostgreSQL via SQLAlchemy async."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    @staticmethod
    def _current_user_id() -> str | None:
        """Return the ``current_user_id`` contextvar value or ``None``."""
        return current_user_id.get()

    async def _assert_thread_exists(self, session: AsyncSession, thread_id: str) -> ThreadModel:
        """Return the parent thread row, filtered by ``user_id`` when set.

        Raises:
            ThreadNotFoundError: If the thread does not exist (or is owned by
                another user when the contextvar is set).
        """
        uid = self._current_user_id()
        if uid is None:
            thread = await session.get(ThreadModel, thread_id)
        else:
            stmt = select(ThreadModel).where(ThreadModel.id == thread_id, ThreadModel.user_id == uid)
            thread = (await session.execute(stmt)).scalar_one_or_none()
        if thread is None:
            raise ThreadNotFoundError(ErrorMessage.THREAD_NOT_FOUND.format(thread_id=thread_id))
        return thread

    async def add(self, thread_id: str, event: TraceEvent) -> None:
        """Persist a single trace event.

        Args:
            thread_id: Parent thread id.
            event: The trace event to persist.

        Raises:
            ThreadNotFoundError: If the thread does not exist.
            StorageError: On infrastructure failure.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                thread = await self._assert_thread_exists(session, thread_id)
                session.add(self._to_model(event, user_id=thread.user_id))
                await session.commit()
            except ThreadNotFoundError:
                raise
            except SQLAlchemyError as e:
                raise StorageError(ErrorMessage.TRACE_FAILED_ADD.format(thread_id=thread_id, error=e)) from e

    async def add_batch(self, thread_id: str, events: list[TraceEvent]) -> None:
        """Persist a batch of trace events atomically.

        Uses ``session.add_all`` for a single round-trip insert.

        Args:
            thread_id: Parent thread id.
            events: The trace events to persist.

        Raises:
            ThreadNotFoundError: If the thread does not exist.
            StorageError: On infrastructure failure.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                thread = await self._assert_thread_exists(session, thread_id)
                session.add_all([self._to_model(e, user_id=thread.user_id) for e in events])
                await session.commit()
            except ThreadNotFoundError:
                raise
            except SQLAlchemyError as e:
                raise StorageError(ErrorMessage.TRACE_FAILED_ADD_BATCH.format(thread_id=thread_id, error=e)) from e

    async def list_by_thread(self, thread_id: str) -> list[TraceEvent]:
        """List all trace events for a thread, ordered by timestamp.

        Args:
            thread_id: Parent thread id.

        Returns:
            A list of TraceEvent ordered by timestamp (oldest first).

        Raises:
            ThreadNotFoundError: If the thread does not exist.
            StorageError: On infrastructure failure.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                await self._assert_thread_exists(session, thread_id)
                result = await session.execute(
                    select(TraceEventModel)
                    .where(TraceEventModel.thread_id == thread_id)
                    .order_by(TraceEventModel.timestamp, TraceEventModel.sequence)
                )
                return [_model_to_event(m) for m in result.scalars().all()]
            except ThreadNotFoundError:
                raise
            except SQLAlchemyError as e:
                raise StorageError(ErrorMessage.TRACE_FAILED_LIST.format(thread_id=thread_id, error=e)) from e

    async def list_by_turn(self, thread_id: str, turn_id: str) -> list[TraceEvent]:
        """List trace events for a specific turn of a thread.

        Args:
            thread_id: Parent thread id.
            turn_id: Turn identifier.

        Returns:
            A list of TraceEvent ordered by timestamp.

        Raises:
            StorageError: On infrastructure failure.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                result = await session.execute(
                    select(TraceEventModel)
                    .where(TraceEventModel.thread_id == thread_id)
                    .where(TraceEventModel.turn_id == turn_id)
                    .order_by(TraceEventModel.timestamp, TraceEventModel.sequence)
                )
                return [_model_to_event(m) for m in result.scalars().all()]
            except SQLAlchemyError as e:
                raise StorageError(ErrorMessage.TRACE_FAILED_LIST.format(thread_id=thread_id, error=e)) from e

    async def list_messages(self, thread_id: str) -> list[TraceEvent]:
        """List only HUMAN_MESSAGE + AI_MESSAGE events for a thread.

        Args:
            thread_id: Parent thread id.

        Returns:
            A list of TraceEvent filtered to HUMAN_MESSAGE + AI_MESSAGE,
            ordered by timestamp (oldest first).

        Raises:
            StorageError: On infrastructure failure.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                result = await session.execute(
                    select(TraceEventModel)
                    .where(TraceEventModel.thread_id == thread_id)
                    .where(
                        TraceEventModel.type.in_([TraceEventType.HUMAN_MESSAGE.value, TraceEventType.AI_MESSAGE.value])
                    )
                    .order_by(TraceEventModel.timestamp, TraceEventModel.sequence)
                )
                return [_model_to_event(m) for m in result.scalars().all()]
            except SQLAlchemyError as e:
                raise StorageError(ErrorMessage.TRACE_FAILED_LIST.format(thread_id=thread_id, error=e)) from e

    @staticmethod
    def _to_model(event: TraceEvent, *, user_id: str = "") -> TraceEventModel:
        """Convert a domain TraceEvent to its ORM model.

        Args:
            event: The domain event to convert.
            user_id: Owner to denormalize onto the row (defaults to ``""``).
        """
        return TraceEventModel(
            id=event.id,
            thread_id=event.thread_id,
            turn_id=event.turn_id,
            type=event.type.value,
            source=event.source,
            name=event.name,
            content=event.content,
            event_metadata=event.metadata,
            timestamp=event.timestamp,
            sequence=event.sequence,
            user_id=user_id,
        )
