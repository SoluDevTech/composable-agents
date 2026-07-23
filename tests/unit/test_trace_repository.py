"""Tests for PostgresTraceEventRepository against a real in-memory SQLite engine."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.domain.entities.trace_event import TraceEvent, TraceEventType
from src.domain.errors.thread import ThreadNotFoundError


def _make_event(
    thread_id: str,
    turn_id: str,
    type_: TraceEventType,
    *,
    content: str | None = None,
    sequence: int = 0,
    timestamp: datetime | None = None,
    source: str | None = None,
    name: str | None = None,
    metadata: dict | None = None,
) -> TraceEvent:
    return TraceEvent(
        id=str(uuid4()),
        thread_id=thread_id,
        turn_id=turn_id,
        type=type_,
        content=content,
        source=source,
        name=name,
        metadata=metadata,
        timestamp=timestamp or datetime.now(UTC),
        sequence=sequence,
    )


class TestPostgresTraceEventRepository:
    async def test_add_persists_event_and_list_by_thread_returns_it(self, thread_repo, trace_repo):
        # Arrange
        thread = await thread_repo.create("test-agent")
        event = _make_event(thread.id, "turn-1", TraceEventType.HUMAN_MESSAGE, content="hello")

        # Act
        await trace_repo.add(thread.id, event)
        events = await trace_repo.list_by_thread(thread.id)

        # Assert
        assert len(events) == 1
        assert events[0].thread_id == thread.id
        assert events[0].type == TraceEventType.HUMAN_MESSAGE
        assert events[0].content == "hello"
        assert events[0].turn_id == "turn-1"

    async def test_add_batch_persists_multiple_events(self, thread_repo, trace_repo):
        # Arrange
        thread = await thread_repo.create("test-agent")
        events = [
            _make_event(thread.id, "turn-1", TraceEventType.HUMAN_MESSAGE, content="hi", sequence=0),
            _make_event(thread.id, "turn-1", TraceEventType.AI_MESSAGE, content='{"content":"hi back"}', sequence=1),
            _make_event(thread.id, "turn-1", TraceEventType.THINKING, content="thinking", sequence=2),
        ]

        # Act
        await trace_repo.add_batch(thread.id, events)
        result = await trace_repo.list_by_thread(thread.id)

        # Assert
        assert len(result) == 3

    async def test_list_by_turn_filters_by_turn_id(self, thread_repo, trace_repo):
        # Arrange
        thread = await thread_repo.create("test-agent")
        await trace_repo.add_batch(
            thread.id,
            [
                _make_event(thread.id, "turn-1", TraceEventType.HUMAN_MESSAGE, content="m1", sequence=0),
                _make_event(thread.id, "turn-2", TraceEventType.HUMAN_MESSAGE, content="m2", sequence=1),
                _make_event(thread.id, "turn-1", TraceEventType.AI_MESSAGE, content='{"content":"r1"}', sequence=2),
            ],
        )

        # Act
        result = await trace_repo.list_by_turn(thread.id, "turn-1")

        # Assert
        assert len(result) == 2
        assert all(e.turn_id == "turn-1" for e in result)

    async def test_list_messages_returns_only_human_and_ai_sorted_by_timestamp(self, thread_repo, trace_repo):
        # Arrange
        thread = await thread_repo.create("test-agent")
        early = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        mid = datetime(2025, 1, 1, 10, 0, 5, tzinfo=UTC)
        late = datetime(2025, 1, 1, 10, 0, 10, tzinfo=UTC)
        await trace_repo.add_batch(
            thread.id,
            [
                _make_event(thread.id, "turn-1", TraceEventType.THINKING, content="t", sequence=0, timestamp=mid),
                _make_event(
                    thread.id,
                    "turn-1",
                    TraceEventType.AI_MESSAGE,
                    content='{"content":"late"}',
                    sequence=2,
                    timestamp=late,
                ),
                _make_event(
                    thread.id, "turn-1", TraceEventType.HUMAN_MESSAGE, content="early", sequence=1, timestamp=early
                ),
                _make_event(thread.id, "turn-1", TraceEventType.TOOL_CALL, content="tool", sequence=3, timestamp=mid),
            ],
        )

        # Act
        result = await trace_repo.list_messages(thread.id)

        # Assert
        assert len(result) == 2
        assert [r.type for r in result] == [TraceEventType.HUMAN_MESSAGE, TraceEventType.AI_MESSAGE]
        assert [r.content for r in result] == ["early", '{"content":"late"}']

    async def test_add_raises_thread_not_found_when_thread_missing(self, trace_repo):
        # Arrange
        event = _make_event("nonexistent", "turn-1", TraceEventType.HUMAN_MESSAGE, content="hi")

        # Act / Assert
        with pytest.raises(ThreadNotFoundError):
            await trace_repo.add("nonexistent", event)

    async def test_add_batch_raises_thread_not_found_when_thread_missing(self, trace_repo):
        # Arrange
        events = [_make_event("nonexistent", "turn-1", TraceEventType.HUMAN_MESSAGE, content="hi")]

        # Act / Assert
        with pytest.raises(ThreadNotFoundError):
            await trace_repo.add_batch("nonexistent", events)

    async def test_list_by_thread_returns_empty_for_thread_without_events(self, thread_repo, trace_repo):
        # Arrange
        thread = await thread_repo.create("test-agent")

        # Act
        result = await trace_repo.list_by_thread(thread.id)

        # Assert
        assert result == []

    async def test_list_messages_returns_empty_when_no_messages(self, thread_repo, trace_repo):
        # Arrange
        thread = await thread_repo.create("test-agent")
        await trace_repo.add(
            thread.id,
            _make_event(thread.id, "turn-1", TraceEventType.THINKING, content="t"),
        )

        # Act
        result = await trace_repo.list_messages(thread.id)

        # Assert
        assert result == []
