"""Outbound port: TraceEventRepository.

Persistence boundary for :class:`~src.domain.entities.trace_event.TraceEvent`.
The repository is the single source of truth for everything that happened inside
a thread; ``Message`` projections are rebuilt from the HUMAN_MESSAGE + AI_MESSAGE
events.
"""

from abc import ABC, abstractmethod

from src.domain.entities.trace_event import TraceEvent


class TraceEventRepository(ABC):
    """Outbound port for persisting and retrieving trace events."""

    @abstractmethod
    async def add(self, thread_id: str, event: TraceEvent) -> None:
        """Persist a single trace event.

        Args:
            thread_id: Parent thread id.
            event: The trace event to persist.

        Raises:
            ThreadNotFoundError: If the thread does not exist.
            StorageError: On infrastructure failure.
        """
        ...

    @abstractmethod
    async def add_batch(self, thread_id: str, events: list[TraceEvent]) -> None:
        """Persist a batch of trace events atomically.

        Args:
            thread_id: Parent thread id.
            events: The trace events to persist.

        Raises:
            ThreadNotFoundError: If the thread does not exist.
            StorageError: On infrastructure failure.
        """
        ...

    @abstractmethod
    async def list_by_thread(self, thread_id: str) -> list[TraceEvent]:
        """List all trace events for a thread, ordered by timestamp.

        Args:
            thread_id: Parent thread id.

        Returns:
            A list of TraceEvent ordered by timestamp (oldest first).
        """
        ...

    @abstractmethod
    async def list_by_turn(self, thread_id: str, turn_id: str) -> list[TraceEvent]:
        """List trace events for a specific turn of a thread.

        Args:
            thread_id: Parent thread id.
            turn_id: Turn identifier.

        Returns:
            A list of TraceEvent ordered by timestamp.
        """
        ...

    @abstractmethod
    async def list_messages(self, thread_id: str) -> list[TraceEvent]:
        """List only HUMAN_MESSAGE + AI_MESSAGE events for a thread.

        Used to rebuild the backward-compatible ``Message`` projection.

        Args:
            thread_id: Parent thread id.

        Returns:
            A list of TraceEvent filtered to HUMAN_MESSAGE + AI_MESSAGE,
            ordered by timestamp (oldest first).
        """
        ...
