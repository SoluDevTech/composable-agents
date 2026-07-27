"""Tests for per-user isolation in :class:`PostgresTraceEventRepository`.

The repository filters trace events by the parent thread's ``user_id`` when
``current_user_id`` is set, so a user can only list events on threads they
own. When the contextvar is ``None`` no filter is applied.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.domain.entities.trace_event import TraceEvent, TraceEventType
from src.domain.errors.thread import ThreadNotFoundError
from src.infrastructure.database.rls_context import current_user_id


def _make_event(
    thread_id: str, turn_id: str, type_: TraceEventType, *, content: str | None = None, sequence: int = 0
) -> TraceEvent:
    return TraceEvent(
        id=str(uuid4()),
        thread_id=thread_id,
        turn_id=turn_id,
        type=type_,
        content=content,
        timestamp=datetime.now(UTC),
        sequence=sequence,
    )


class TestTraceEventUserIsolation:
    """Trace events inherit isolation from their parent thread."""

    async def test_add_batch_under_uA_persists_events(self, thread_repo, trace_repo):
        # Arrange
        tok = current_user_id.set("uA")
        try:
            thread = await thread_repo.create("agent-a")
            events = [
                _make_event(thread.id, "turn-1", TraceEventType.HUMAN_MESSAGE, content="hi", sequence=0),
                _make_event(thread.id, "turn-1", TraceEventType.AI_MESSAGE, content="bye", sequence=1),
            ]
            await trace_repo.add_batch(thread.id, events)
            listed = await trace_repo.list_by_thread(thread.id)
        finally:
            current_user_id.reset(tok)

        # Assert
        assert len(listed) == 2

    async def test_list_by_thread_under_uB_raises_for_uA_thread(self, thread_repo, trace_repo):
        # Arrange — uA owns the thread
        tok = current_user_id.set("uA")
        try:
            thread = await thread_repo.create("agent-a")
        finally:
            current_user_id.reset(tok)

        # Act / Assert — uB cannot see uA's thread → ThreadNotFoundError
        tok_b = current_user_id.set("uB")
        try:
            with pytest.raises(ThreadNotFoundError):
                await trace_repo.list_by_thread(thread.id)
        finally:
            current_user_id.reset(tok_b)

    async def test_add_under_uB_to_uA_thread_raises(self, thread_repo, trace_repo):
        # Arrange
        tok = current_user_id.set("uA")
        try:
            thread = await thread_repo.create("agent-a")
        finally:
            current_user_id.reset(tok)

        # Act / Assert
        tok_b = current_user_id.set("uB")
        try:
            event = _make_event(thread.id, "turn-1", TraceEventType.HUMAN_MESSAGE, content="hi")
            with pytest.raises(ThreadNotFoundError):
                await trace_repo.add(thread.id, event)
        finally:
            current_user_id.reset(tok_b)

    async def test_list_by_thread_no_contextvar_returns_all(self, thread_repo, trace_repo):
        # Arrange — create under uA then read with no contextvar
        tok = current_user_id.set("uA")
        try:
            thread = await thread_repo.create("agent-a")
            await trace_repo.add(
                thread.id, _make_event(thread.id, "turn-1", TraceEventType.HUMAN_MESSAGE, content="hi")
            )
        finally:
            current_user_id.reset(tok)

        # Act — no contextvar
        assert current_user_id.get() is None
        events = await trace_repo.list_by_thread(thread.id)

        # Assert — visible (no filter)
        assert len(events) == 1
