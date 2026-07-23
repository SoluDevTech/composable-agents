"""Tests for TraceEvent domain entity and Message.from_trace_event factory."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.domain.entities.message import Message, MessageRole, MessageStatus
from src.domain.entities.trace_event import TraceEvent, TraceEventType


class TestTraceEvent:
    """Tests for TraceEvent entity."""

    def test_frozen_entity_cannot_be_mutated(self):
        # Arrange
        event = TraceEvent(
            id="evt-1",
            thread_id="thread-1",
            turn_id="turn-1",
            type=TraceEventType.HUMAN_MESSAGE,
            content="hello",
            timestamp=datetime(2025, 1, 1, tzinfo=UTC),
            sequence=0,
        )

        # Act / Assert
        with pytest.raises(ValidationError):
            event.content = "mutated"  # type: ignore[misc]

    def test_validates_event_type(self):
        # Arrange / Act / Assert
        with pytest.raises(ValidationError):
            TraceEvent(
                id="evt-1",
                thread_id="thread-1",
                turn_id="turn-1",
                type="not_a_real_type",  # type: ignore[arg-type]
                content="hello",
                timestamp=datetime(2025, 1, 1, tzinfo=UTC),
                sequence=0,
            )

    def test_optional_fields_default_to_none(self):
        # Arrange / Act
        event = TraceEvent(
            id="evt-1",
            thread_id="thread-1",
            turn_id="turn-1",
            type=TraceEventType.HUMAN_MESSAGE,
            content="hello",
            timestamp=datetime(2025, 1, 1, tzinfo=UTC),
            sequence=0,
        )

        # Assert
        assert event.source is None
        assert event.name is None
        assert event.metadata is None


class TestMessageFromTraceEvent:
    """Tests for Message.from_trace_event static factory."""

    def test_human_message_event_reconstructs_human_message(self):
        # Arrange
        ts = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        event = TraceEvent(
            id="evt-1",
            thread_id="thread-1",
            turn_id="turn-1",
            type=TraceEventType.HUMAN_MESSAGE,
            content="Hello agent!",
            timestamp=ts,
            sequence=0,
        )

        # Act
        msg = Message.from_trace_event(event)

        # Assert
        assert msg.role == MessageRole.HUMAN
        assert msg.content == "Hello agent!"
        assert msg.timestamp == ts
        assert msg.turn_id == "turn-1"
        assert msg.tool_calls is None
        assert msg.status is None
        assert msg.structured_response is None
        assert msg.thinking is None

    def test_ai_message_event_reconstructs_full_ai_message(self):
        # Arrange
        ts = datetime(2025, 1, 1, 12, 0, 5, tzinfo=UTC)
        payload = {
            "content": "Analysis complete",
            "tool_calls": [{"name": "search", "args": {"q": "x"}, "id": "c1"}],
            "status": "completed",
            "structured_response": {"score": 95},
            "thinking": "I should search first",
        }
        event = TraceEvent(
            id="evt-2",
            thread_id="thread-1",
            turn_id="turn-1",
            type=TraceEventType.AI_MESSAGE,
            content=__import__("json").dumps(payload),
            timestamp=ts,
            sequence=1,
        )

        # Act
        msg = Message.from_trace_event(event)

        # Assert
        assert msg.role == MessageRole.AI
        assert msg.content == "Analysis complete"
        assert msg.timestamp == ts
        assert msg.turn_id == "turn-1"
        assert msg.tool_calls == [{"name": "search", "args": {"q": "x"}, "id": "c1"}]
        assert msg.status == MessageStatus.COMPLETED
        assert msg.structured_response == {"score": 95}
        assert msg.thinking == "I should search first"

    def test_ai_message_event_with_minimal_payload(self):
        # Arrange
        ts = datetime(2025, 1, 1, 12, 0, 5, tzinfo=UTC)
        event = TraceEvent(
            id="evt-3",
            thread_id="thread-1",
            turn_id="turn-2",
            type=TraceEventType.AI_MESSAGE,
            content="{}",  # empty payload
            timestamp=ts,
            sequence=1,
        )

        # Act
        msg = Message.from_trace_event(event)

        # Assert
        assert msg.role == MessageRole.AI
        assert msg.content is None
        assert msg.turn_id == "turn-2"
        assert msg.tool_calls is None
        assert msg.status is None
        assert msg.structured_response is None
        assert msg.thinking is None
