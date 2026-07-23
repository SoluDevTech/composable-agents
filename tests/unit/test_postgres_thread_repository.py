"""Tests for PostgresThreadRepository against a real in-memory SQLite engine."""

import json
from datetime import UTC, datetime

import pytest

from src.domain.entities.message import MessageRole, MessageStatus
from src.domain.entities.thread import Thread
from src.domain.entities.trace_event import TraceEvent, TraceEventType
from src.domain.errors.thread import ThreadNotFoundError


def _make_trace_event(
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
    from uuid import uuid4

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


class TestPostgresThreadRepository:
    async def test_create_returns_thread_with_empty_trace_events(self, thread_repo):
        # Act
        result = await thread_repo.create("test-agent")

        # Assert
        assert isinstance(result, Thread)
        assert result.agent_name == "test-agent"
        assert result.trace_events == []
        assert result.id is not None

    async def test_get_returns_persisted_thread_with_messages_reconstructed(self, thread_repo, trace_repo):
        # Arrange
        created = await thread_repo.create("test-agent")
        await trace_repo.add(
            created.id,
            _make_trace_event(
                created.id,
                "turn-1",
                TraceEventType.HUMAN_MESSAGE,
                content="hello",
            ),
        )

        # Act
        result = await thread_repo.get(created.id)

        # Assert
        assert isinstance(result, Thread)
        assert result.id == created.id
        assert result.agent_name == "test-agent"
        assert len(result.trace_events) == 1
        assert result.trace_events[0].content == "hello"
        # Backward compat: messages computed from trace_events
        assert len(result.messages) == 1
        assert result.messages[0].content == "hello"
        assert result.messages[0].role == MessageRole.HUMAN

    async def test_get_not_found_raises(self, thread_repo):
        # Arrange
        # (no thread)

        # Act / Assert
        with pytest.raises(ThreadNotFoundError):
            await thread_repo.get("nonexistent-id")

    async def test_list_all_returns_all_threads(self, thread_repo):
        # Arrange
        await thread_repo.create("agent-a")
        await thread_repo.create("agent-b")

        # Act
        result = await thread_repo.list_all()

        # Assert
        assert len(result) == 2
        assert all(isinstance(t, Thread) for t in result)
        agent_names = {t.agent_name for t in result}
        assert agent_names == {"agent-a", "agent-b"}

    async def test_list_all_returns_empty_when_no_threads(self, thread_repo):
        # Arrange
        # (no threads)

        # Act
        result = await thread_repo.list_all()

        # Assert
        assert result == []

    async def test_delete_removes_thread(self, thread_repo):
        # Arrange
        created = await thread_repo.create("test-agent")

        # Act
        await thread_repo.delete(created.id)

        # Assert
        with pytest.raises(ThreadNotFoundError):
            await thread_repo.get(created.id)

    async def test_delete_not_found_raises(self, thread_repo):
        # Arrange
        # (no thread)

        # Act / Assert
        with pytest.raises(ThreadNotFoundError):
            await thread_repo.delete("nonexistent-id")

    async def test_messages_ordered_by_timestamp_via_trace_events(self, thread_repo, trace_repo):
        # Arrange
        created = await thread_repo.create("test-agent")
        earlier = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        later = datetime(2025, 1, 1, 11, 0, 0, tzinfo=UTC)
        await trace_repo.add(
            created.id,
            _make_trace_event(
                created.id,
                "turn-1",
                TraceEventType.AI_MESSAGE,
                content=json.dumps({"content": "late"}),
                sequence=1,
                timestamp=later,
            ),
        )
        await trace_repo.add(
            created.id,
            _make_trace_event(
                created.id,
                "turn-1",
                TraceEventType.HUMAN_MESSAGE,
                content="early",
                sequence=0,
                timestamp=earlier,
            ),
        )

        # Act
        result = await thread_repo.get(created.id)

        # Assert
        assert [m.content for m in result.messages] == ["early", "late"]

    async def test_ai_message_roundtrip_preserves_all_fields(self, thread_repo, trace_repo):
        # Arrange
        created = await thread_repo.create("analyzer")
        now = datetime.now(UTC)
        payload = {
            "content": "Analysis complete",
            "tool_calls": None,
            "status": "completed",
            "structured_response": {"score": 95, "label": "pass"},
        }
        await trace_repo.add(
            created.id,
            _make_trace_event(
                created.id,
                "turn-1",
                TraceEventType.AI_MESSAGE,
                content=json.dumps(payload),
                sequence=0,
                timestamp=now,
            ),
        )

        # Act
        result = await thread_repo.get(created.id)

        # Assert
        roundtripped = result.messages[0]
        assert roundtripped.role == MessageRole.AI
        assert roundtripped.content == "Analysis complete"
        assert roundtripped.status == MessageStatus.COMPLETED
        assert roundtripped.structured_response == {"score": 95, "label": "pass"}

    async def test_ai_message_with_tool_calls_survives_roundtrip(self, thread_repo, trace_repo):
        # Arrange
        created = await thread_repo.create("search-agent")
        tool_calls_data = [
            {"name": "search_documents", "args": {"query": "python asyncio", "limit": 10}, "id": "call_abc123"},
            {"name": "fetch_url", "args": {"url": "https://docs.python.org"}, "id": "call_def456"},
        ]
        payload = {
            "content": "Let me search for that.",
            "tool_calls": tool_calls_data,
        }
        await trace_repo.add(
            created.id,
            _make_trace_event(
                created.id,
                "turn-1",
                TraceEventType.AI_MESSAGE,
                content=json.dumps(payload),
                sequence=0,
            ),
        )

        # Act
        result = await thread_repo.get(created.id)

        # Assert
        roundtripped = result.messages[0]
        assert roundtripped.tool_calls == tool_calls_data
        assert roundtripped.tool_calls[0]["args"]["query"] == "python asyncio"
        assert roundtripped.tool_calls[1]["id"] == "call_def456"
